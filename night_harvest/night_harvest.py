#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
night_harvest.py — «حصاد الليل»: CI كمنتج (الفكرة 2 من خطة التطوير — فورية).
مهمة يومية مجدولة تجري فحوص المسار (فحص TED + قلب PDF عينة + فحص نقطة API)،
تسجل كل يوم بخط زمني JSON دائم، تحتسب السلسلة المتصلة (streak)، تقارن بأداء
الأيام السابقة (خط أساس 7 أيام)، وتشغل إنذاراً عند أي تدهور أو فشل.

فلسفة KPI المعتمد: «30 يوماً متتالية من حصاد يومي ناجح دون تدخل بشري» —
السلسلة تُحتسب من الملفات الموقعة زمنياً ولا تُصفَّر إلا بفشل فعلي.

الاستخدام:
    python night_harvest.py --init            # إنشاء harvest_config.json نموذجي
    python night_harvest.py                   # تنفيذ حصاد اليوم وتحديث السلسلة
    python night_harvest.py --status          # عرض السلسلة وآخر النتائج دون تنفيذ
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATUS_DIR = BASE / "status"
CONFIG = BASE / "harvest_config.json"
DEFAULT_CONFIG = {
    "checks": [
        {"name": "api_endpoint_alive", "cmd": "curl -fsS -m 20 -o /dev/null https://<عنوان-glossary-api-بعد-النشر>/health || exit 1", "critical": True},
        {"name": "ted_subtitle_fetch_sample", "cmd": "python -m marathon_ted_pipeline.checks.ted_fetch --sample 1", "critical": True},
        {"name": "pdf_pipeline_sample", "cmd": "python -m marathon_ted_pipeline.checks.pdf_sample --pages 1", "critical": False}
    ],
    "baseline_days": 7,
    "max_duration_ratio": 2.0,
    "owner": "DrAbdulmalek",
    "repo": "marathon_ted_pipeline"
}


def load_config() -> dict:
    if not CONFIG.exists():
        sys.exit("✗ لا يوجد harvest_config.json — ابدأ بـ: python night_harvest.py --init")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def today_key() -> str:
    return time.strftime("%Y-%m-%d")


def run_check(check: dict) -> dict:
    """تشغيل فحص واحد: رمز الخروج، المدة، ذيل المخرجات (للتشخيص لا للعرض الكامل)."""
    t0 = time.time()
    try:
        cp = subprocess.run(check["cmd"], shell=True, capture_output=True,  # noqa: S602
                            text=True, timeout=900)
        tail = (cp.stderr or cp.stdout or "").strip().splitlines()[-3:]
        return {"name": check["name"], "ok": cp.returncode == 0,
                "seconds": round(time.time() - t0, 1),
                "tail": " | ".join(tail)[-200:]}
    except subprocess.TimeoutExpired:
        return {"name": check["name"], "ok": False, "seconds": 900.0, "tail": "timeout 900s"}


def load_history() -> list:
    files = sorted(STATUS_DIR.glob("????-??-??.json"))
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def compute_streak(history: list) -> int:
    """أطول سلسلة أيام ناجحة متتالية منتهية بأحدث يوم (ناجح أو لا يُحتسب)."""
    days = {h["date"]: h["all_ok"] for h in history}
    streak, d = 0, time.time()
    while True:
        key = time.strftime("%Y-%m-%d", time.gmtime(d))
        if key in days:
            if not days[key]:
                break
            streak += 1
        elif streak:  # يوم غائب في المنتصف يقطع السلسلة
            break
        d -= 86400
        if streak > 400:
            break
    return streak


def baseline_duration(history: list, days: int) -> float:
    """متوسط مدة أيام النجاح الأخيرة — أساس كشف التدهور البطيء."""
    vals = [h["total_seconds"] for h in history[-days:] if h.get("all_ok") and h.get("total_seconds")]
    return statistics.mean(vals) if vals else 0.0


def harvest() -> dict:
    cfg = load_config()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    checks = [run_check(c) for c in cfg["checks"]]
    record = {
        "date": today_key(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks if c.get("critical", True)),
        "total_seconds": round(sum(c["seconds"] for c in checks), 1),
    }
    history = [h for h in load_history() if h["date"] != record["date"]] + [record]
    record["streak"] = compute_streak(history)
    base = baseline_duration(history[:-1], cfg.get("baseline_days", 7))
    record["baseline_seconds"] = round(base, 1)
    record["degraded"] = bool(base and record["all_ok"]
                              and record["total_seconds"] > base * cfg.get("max_duration_ratio", 2.0))
    (STATUS_DIR / f"{record['date']}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    (STATUS_DIR / "streak.json").write_text(
        json.dumps({"streak": record["streak"], "last_date": record["date"],
                    "last_ok": record["all_ok"], "degraded": record["degraded"]},
                   ensure_ascii=False), encoding="utf-8")
    print(f"الحصاد {record['date']}: {'✓ ناجح' if record['all_ok'] else '✗ فشل'}"
          f" | السلسلة: {record['streak']} يوماً | المدة: {record['total_seconds']}s"
          f" | خط الأساس: {record['baseline_seconds']}s"
          f"{' | ⚠ تدهور أداء' if record['degraded'] else ''}")
    for c in checks:
        print(f"  • {c['name']}: {'✓' if c['ok'] else '✗'} ({c['seconds']}s) {c['tail']}")
    if not record["all_ok"] or record["degraded"]:
        alert = STATUS_DIR / f"alert-{record['date']}.md"
        alert.write_text(
            f"# إنذار حصاد الليل — {record['date']}\n\n"
            f"- النتيجة: {'فشل فحص' if not record['all_ok'] else 'تدهور زمني (أبطأ من خط الأساس ×'+str(cfg.get('max_duration_ratio', 2.0))+')'}\n"
            f"- السلسلة قبل اليوم: انقطعت عند {record['streak']} يوماً\n"
            f"- التفاصيل: {json.dumps(record['checks'], ensure_ascii=False, indent=1)}\n",
            encoding="utf-8")
        print(f"⚠ كُتب الإنذار: {alert}")
        return 1
    return 0


def show_status() -> None:
    streak_file = STATUS_DIR / "streak.json"
    if streak_file.exists():
        print(json.dumps(json.loads(streak_file.read_text(encoding="utf-8")),
                         ensure_ascii=False, indent=1))
    history = load_history()[-10:]
    for h in history:
        print(f"  {h['date']}: {'✓' if h.get('all_ok') else '✗'} {h.get('total_seconds')}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.init:
        if CONFIG.exists():
            print(f"• الملف موجود — لم يُمَس: {CONFIG}")
        else:
            CONFIG.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=1),
                              encoding="utf-8")
            print(f"✓ أُنشئ النموذج: {CONFIG} — عدّل أوامر الفحص إلى مسار pipeline فعلي.")
        return 0
    if args.status:
        show_status()
        return 0
    return harvest()


if __name__ == "__main__":
    sys.exit(main())
