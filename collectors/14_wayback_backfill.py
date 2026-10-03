#!/usr/bin/env python3
"""
14_wayback_backfill.py — استرجاع معرفات hls القديمة من Wayback Machine.

المشكلة: 5,819 محادثة في talks.json بلا معرف حي في hls.ted.com (المساحة /talks/).
الفرضية: لقطات Internet Archive لصفحات ted.com/talks/{slug} القديمة تحوي
         المعرف القديم في HTML (talkId / project_masters/N / talks/view/id/N).
التصميم: لا يخرج أي معرف إلا إذا أثبت حيويته على hls.ted.com مباشرة (200).

الاستخدام (على جهاز يصل إلى web.archive.org):
    # اختبار يدوي سريع أولًا (15 دقيقة كما اقترح ديبسيك):
    curl -s "http://web.archive.org/cdx/search/cdx?url=ted.com/talks/sir_ken_robinson_do_schools_kill_creativity&output=json&limit=5"
    python3 collect/14_wayback_backfill.py --limit 20 --workers 1   # عينة
    # إن كانت النسبة جيدة (>=40% verified):
    nohup python3 collect/14_wayback_backfill.py --workers 2 \\
        > logs/wayback_backfill.log 2>&1 &
    # الناتج: data/talk_id_map.json + data/talks_wayback.json
    # الحملة الموسعة بعدها:
    python3 collect/02_download_subtitles.py --talks-file data/talks_wayback.json \\
        --langs en,ar --workers 5 --delay 0.5

المخرجات:
    data/talk_id_map.json   {slug: {status, legacy_id, verified, snapshot_ts, pattern}}
    data/talks_wayback.json قائمة بنفس مخطط talks_alive.json (للحملة)
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
try:
    from ted_utils import DATA, HEADERS, load_json, save_json
except Exception:  # وضع مستقل بلا ted_utils
    DATA = HERE.parent / "data"
    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"}
    def load_json(p):
        p = Path(p)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    def save_json(p, obj):
        Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                           encoding="utf-8")

CDX = "http://web.archive.org/cdx/search/cdx"
SNAP = "http://web.archive.org/web/{ts}/{url}"
HLS_CHECK = "https://hls.ted.com/talks/{tid}/subtitles/en/full.vtt"

# أنماط استخراج المعرف القديم من HTML المؤرشف (الأقدم أولًا = أصدق)
PATTERNS = [
    ("talkId_json",   re.compile(r'"talkId"\s*:\s*(\d+)')),
    ("talkId_loose",  re.compile(r'talkId["\':=\s]+(\d+)')),
    ("project_masters", re.compile(r'project_masters/(\d+)')),
    ("view_id",       re.compile(r'/talks/view/id/(\d+)')),
]

MAP_LOCK = Lock()


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def cdx_snapshots(session, slug: str, fetch_delay: float, retries: int = 2):
    """أعد قائمة طوابع زمنية (الأقدم أولًا) لصفحة slug. جرّب غير-www ثم www."""
    for prefix in ("ted.com", "www.ted.com"):
        url = f"{CDX}?url={prefix}/talks/{slug}&output=json&limit=6&filter=statuscode:200"
        for attempt in range(retries + 1):
            try:
                r = session.get(url, timeout=30)
                if r.status_code == 200:
                    rows = r.json()
                    if isinstance(rows, list) and len(rows) > 1:
                        # الصف الأول رأس الأعمدة؛ الطوابع في العمود [1]
                        return [row[1] for row in rows[1:]]
                    break  # فارغة لهذه البادئة -> جرّب التالية
                time.sleep(fetch_delay * (attempt + 1))
            except Exception:
                time.sleep(fetch_delay * (attempt + 1))
        time.sleep(fetch_delay)
    return []


def extract_ids(html: str):
    """أعد [(pattern_name, id)] فريدة بالترتيب."""
    found, seen = [], set()
    for name, rx in PATTERNS:
        for m in rx.finditer(html):
            tid = m.group(1)
            if tid not in seen:
                seen.add(tid)
                found.append((name, tid))
    return found


def verify_hls(session, tid: str) -> bool:
    """الخطوة الذهبية: المعرف لا قيمة له إلا إذا رد hls بـ 200 اليوم."""
    try:
        r = session.get(HLS_CHECK.format(tid=tid), timeout=20,
                        allow_redirects=False)
        return r.status_code == 200 and len(r.content) > 100
    except Exception:
        return False


def process_slug(slug: str, args, session) -> dict:
    rec = {"status": "no_snapshots", "legacy_id": None, "verified": False,
           "snapshot_ts": None, "pattern": None}
    ts_list = cdx_snapshots(session, slug, args.fetch_delay)
    if not ts_list:
        return rec

    for ts in ts_list:  # الأقدم أولًا — أنظمة المعرفات القديمة
        try:
            r = session.get(SNAP.format(ts=ts, url=f"https://www.ted.com/talks/{slug}"),
                            timeout=45)
            if r.status_code != 200 or len(r.content) < 500:
                time.sleep(args.fetch_delay)
                continue
        except Exception:
            time.sleep(args.fetch_delay)
            continue
        for pattern, tid in extract_ids(r.text[:400_000]):
            if args.no_verify:
                rec.update(status="id_found_unverified", legacy_id=tid,
                           snapshot_ts=ts, pattern=pattern)
                return rec
            if verify_hls(session, tid):
                rec.update(status="verified", legacy_id=tid, verified=True,
                           snapshot_ts=ts, pattern=pattern)
                return rec
            time.sleep(args.fetch_delay)
        time.sleep(args.fetch_delay)

    # لقطات وجدناها لكن لا معرف حي
    rec["status"] = "no_live_id"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DATA / "slugs_missing.json"))
    ap.add_argument("--map-file", default=str(DATA / "talk_id_map.json"))
    ap.add_argument("--out-file", default=str(DATA / "talks_wayback.json"))
    ap.add_argument("--limit", type=int, default=0, help="حد للتجربة (0 = الكل)")
    ap.add_argument("--workers", type=int, default=2,
                    help="خيوط (CDX صارم في المعدل — لا تتجاوز 2-3)")
    ap.add_argument("--fetch-delay", type=float, default=0.6)
    ap.add_argument("--cdx-delay", type=float, default=1.0)
    ap.add_argument("--no-verify", action="store_true",
                    help="استخرج فقط دون فحص hls (غير مستحسن)")
    args = ap.parse_args()

    entries = load_json(args.input) or []
    if args.limit:
        entries = entries[:args.limit]
    slugs = [e["slug"] for e in entries if e.get("slug")]

    the_map = load_json(args.map_file) or {}
    todo = [s for s in slugs if s not in the_map]
    print(f"🎯 الهدف: {len(slugs)} | المتبقي: {len(todo)} "
          f"(مكتمل سابقًا: {len(slugs) - len(todo)})")
    if not todo:
        print("✅ كل شيء مكتمل. أعد بناء القائمة النهائية فقط.")
        write_out(slugs, the_map, args)
        return

    done = ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_slug, s, args, make_session()): s
                for s in todo}
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = {"status": f"error:{e}", "legacy_id": None,
                       "verified": False, "snapshot_ts": None, "pattern": None}
            with MAP_LOCK:
                the_map[slug] = rec
                if done % 10 == 0:
                    save_json(args.map_file, the_map)
            done += 1
            if rec.get("verified"):
                ok += 1
            if done % 25 == 0 or done == len(todo):
                rate = ok / done * 100
                print(f"[{done}/{len(todo)}] verified={ok} ({rate:.0f}%) "
                      f"آخر: {slug[:45]} -> {rec['status']}:{rec['legacy_id']}")
            time.sleep(args.cdx_delay / max(1, args.workers))

    save_json(args.map_file, the_map)
    write_out(slugs, the_map, args)
    verified = sum(1 for v in the_map.values() if v.get("verified"))
    print(f"\n{'=' * 60}\n✅ verified: {verified} معرفًا حيًا مُثبتًا "
          f"من {len(slugs)} slug\n📂 {args.map_file}\n📋 {args.out_file}")


def write_out(slugs, the_map, args):
    """أخرج talks_wayback.json بنفس مخطط talks_alive.json."""
    src = load_json(args.input) or []
    by_slug = {e["slug"]: e for e in src}
    out = [{"id": str(the_map[s]["legacy_id"]), "slug": s,
            "url": f"https://www.ted.com/talks/{s}",
            "title": by_slug.get(s, {}).get("title", ""),
            "src": "wayback"}
           for s in slugs
           if s in the_map and s in by_slug and the_map[s].get("verified")]
    save_json(args.out_file, out)
    print(f"📤 الحملة الجاهزة: {len(out)} مدخلًا -> {args.out_file}")


if __name__ == "__main__":
    main()
