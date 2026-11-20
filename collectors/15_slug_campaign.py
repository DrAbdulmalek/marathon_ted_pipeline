#!/usr/bin/env python3
"""
15_slug_campaign.py — حملة الفضاء الجديد: hls.ted.com/talks/{slug}/ مباشرة.

الدليل (2026-10-03، بايتيًا):
- sir_ken: slug == id 66 (md5 1ec343ce8e30، 30,867B)؛ id 3292 الحديث 404.
- 17/20 slug "مفقود" حية عبر slug؛ العربية حقيقية (2,115-7,833 حرفًا/ملف).
- الفضاءان (id وslug) ينتجان بايتات متطابقة (2/2 willard).
النتيجة: الـ 5,819 "المفقودة" تحتاج slug فقط — بلا خريطة معرفات ولا Wayback.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from ted_utils import (DATA, DOWNLOADS, HEADERS, download_vtt, load_json,
                       save_json)

INPUT_FILE = DATA / "slugs_missing.json"
STATE_FILE = DATA / "download_state_slug.json"
RESULTS_FILE = DATA / "download_results_slug.json"
LOCK = Lock()


def make_session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update(HEADERS)
    return s


def process_slug(slug: str, langs: list, session) -> dict:
    result = {"slug": slug, "subs": {}}
    for lang in langs:
        vtt_path = DOWNLOADS / f"{slug}.{lang}.vtt"
        if vtt_path.exists() and vtt_path.stat().st_size > 50:
            result["subs"][lang] = str(vtt_path)
            continue
        vtt = download_vtt(slug, lang, session)  # slug يمرر كما هو — نفس المسار
        if vtt:
            vtt_path.write_text(vtt, encoding="utf-8")
            result["subs"][lang] = str(vtt_path)
        else:
            result["subs"][lang] = None
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="en,ar")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    slugs = [e["slug"] for e in (load_json(INPUT_FILE) or [])]
    if args.limit:
        slugs = slugs[:args.limit]

    print("=" * 60)
    print(f"🌍 حملة الفضاء الجديد (slug) — {len(slugs)} slug | لغات: {langs}")
    print(f"   Workers: {args.workers} | Delay: {args.delay}s")
    print("=" * 60)

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {
        "completed": {}, "failed": {}}
    completed = state.get("completed", {})

    session_pool = [make_session() for _ in range(args.workers * 2)]
    results, done = [], 0
    total = len(slugs)
    ok_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_slug, s, langs, session_pool[i % len(session_pool)]): s
                for i, s in enumerate(slugs)}
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"slug": slug, "subs": {}, "error": str(e)}
            results.append(r)
            done += 1
            has_any = any(r["subs"].values())
            if has_any:
                completed[slug] = {
                    "subs": {k: bool(v) for k, v in r["subs"].items()},
                    "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                state.setdefault("failed", {}).pop(slug, None)
                ok_count += 1
            else:
                state.setdefault("failed", {})[slug] = {
                    "error": r.get("error", "no_subtitles"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            state["completed"] = completed
            if done % 25 == 0:
                with LOCK:
                    save_json(STATE_FILE, state)
                print(f"[{done}/{total}] ok={ok_count} "
                      f"({ok_count / done * 100:.0f}%) آخر: {slug[:48]}")
            time.sleep(args.delay)

    save_json(STATE_FILE, state)
    save_json(RESULTS_FILE, results)
    en_ok = sum(1 for r in results if r["subs"].get("en"))
    ar_ok = sum(1 for r in results if r["subs"].get("ar"))
    print(f"\n{'=' * 60}")
    print(f"✅ نجح (أي لغة): {ok_count}/{total}")
    print(f"   en={en_ok}  ar={ar_ok}")
    print(f"📂 {DOWNLOADS}\n📋 {STATE_FILE}")


if __name__ == "__main__":
    main()
