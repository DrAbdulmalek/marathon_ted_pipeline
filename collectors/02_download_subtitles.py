#!/usr/bin/env python3
"""
تحميل ترجمات TED (en + ar + لغات أخرى اختيارية).

يستخدم hls.ted.com مباشرة — لا API key، لا تسجيل.
المصدر المؤكد: [7†L21-L23] و [0†L7-L8]

ميزات:
- تنزيل متوازي (ThreadPool) مع rate limiting
- إعادة محاولة تلقائية
- تخطي الملفات المحمّلة مسبقًا
- تسجيل التقدم في ملف JSON
"""
import sys
import time
import json
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, str(Path(__file__).parent))
from ted_utils import (
    DATA, DOWNLOADS, LOGS, HEADERS,
    load_json, save_json, extract_talk_id, download_vtt,
    slug_from_url, safe_filename,
)

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TALKS_FILE = DATA / "talks.json"
STATE_FILE = DATA / "download_state.json"
PROGRESS_LOCK = Lock()

# إعداد جلسة مع إعادة محاولة
def make_session():
    s = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update(HEADERS)
    return s


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"completed": {}, "failed": {}}


def save_state(state: dict):
    with PROGRESS_LOCK:
        save_json(STATE_FILE, state)


def process_talk(talk: dict, langs: list, session: requests.Session) -> dict:
    """حمّل ترجمات محادثة واحدة."""
    slug = talk["slug"]
    talk_url = talk["url"]
    result = {
        "slug": slug, "url": talk_url, "title": talk.get("title", ""),
        "talk_id": talk.get("id", ""), "subs": {},
    }

    # احصل على talk_id إذا لم يكن موجودًا
    tid = result["talk_id"]
    if not tid or not str(tid).isdigit():
        tid = extract_talk_id(talk_url, session)
        if not tid:
            result["error"] = "no_talk_id"
            return result
        result["talk_id"] = tid

    # حمّل كل لغة
    for lang in langs:
        vtt_path = DOWNLOADS / f"{slug}.{lang}.vtt"
        if vtt_path.exists() and vtt_path.stat().st_size > 50:
            result["subs"][lang] = str(vtt_path)
            continue

        vtt = download_vtt(tid, lang, session)
        if vtt:
            vtt_path.write_text(vtt, encoding="utf-8")
            result["subs"][lang] = str(vtt_path)
        else:
            result["subs"][lang] = None

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--langs", default="en,ar",
                        help="لغات مفصولة بفاصلة")
    parser.add_argument("--workers", type=int, default=5,
                        help="عدد الخيوط المتوازية")
    parser.add_argument("--limit", type=int, default=0,
                        help="حد أقصى (0 = بلا حد)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="تأخير بين الطلبات (ثوان)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="أعد المحاولة للفاشلة فقط")
    parser.add_argument("--talks-file", default=None,
                        help="ملف قائمة بديل (افتراضي data/talks.json) — مثال: data/talks_alive.json")
    args = parser.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    print("=" * 60)
    print(f"📥 تحميل ترجمات TED — لغات: {langs}")
    print(f"   Workers: {args.workers} | Delay: {args.delay}s")
    print("=" * 60)

    talks_source = Path(args.talks_file) if args.talks_file else TALKS_FILE
    talks = load_json(talks_source)
    if not talks:
        print(f"❌ لا توجد قائمة في {talks_source}. شغّل 01_get_talk_list.py أولًا.")
        return
    print(f"📋 القائمة: {talks_source} ({len(talks)} محادثة)")

    state = load_state()
    completed = state.get("completed", {})

    # فلترة
    if args.retry_failed:
        failed_slugs = set(state.get("failed", {}).keys())
        talks = [t for t in talks if t["slug"] in failed_slugs]
        print(f"🔄 إعادة المحاولة للفاشلة: {len(talks)}")

    if args.limit > 0:
        talks = talks[:args.limit]

    session = make_session()
    results = []
    done = 0
    total = len(talks)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(process_talk, t, langs, make_session()): t
            for t in talks
        }
        for fut in as_completed(futures):
            done += 1
            try:
                r = fut.result()
            except Exception as e:
                t = futures[fut]
                r = {"slug": t["slug"], "error": str(e), "subs": {}}

            results.append(r)

            # سجّل الحالة
            slug = r["slug"]
            has_any = any(r["subs"].values())
            if has_any:
                completed[slug] = {
                    "talk_id": r.get("talk_id"),
                    "subs": {k: bool(v) for k, v in r["subs"].items()},
                    "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                state.setdefault("failed", {}).pop(slug, None)
            else:
                state.setdefault("failed", {})[slug] = {
                    "error": r.get("error", "no_subtitles"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }

            state["completed"] = completed
            if done % 10 == 0:
                save_state(state)

            # طباعة التقدم
            status = " ".join(
                f"{l}={'✅' if r['subs'].get(l) else '❌'}" for l in langs
            )
            print(f"[{done}/{total}] {slug[:50]:<50} {status}")

            time.sleep(args.delay)

    save_state(state)

    # حفظ النتائج
    save_json(DATA / "download_results.json", results)

    # ملخص
    ok = sum(1 for r in results if any(r["subs"].values()))
    print(f"\n{'=' * 60}")
    print(f"✅ نجح: {ok}/{total}")
    print(f"❌ فشل: {total - ok}/{total}")
    print(f"📂 الملفات في: {DOWNLOADS}")
    print(f"📋 السجل: {STATE_FILE}")


if __name__ == "__main__":
    main()
