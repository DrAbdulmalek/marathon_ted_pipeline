#!/usr/bin/env python3
"""
16_telegram_upload.py — رفع المخرجات إلى القناة الهدف عبر Telethon.

يعمل على الجهاز الذي يملك الجلسة الحقيقية (هذه البيئة بلا بيانات اعتماد:
config.yaml فيه @target_channel_username كـ placeholder، وصفر ملفات .session).

الاستخدام:
    export TELEGRAM_API_ID=12345
    export TELEGRAM_API_HASH=abcdef...
    export TELEGRAM_SESSION=marathon_session          # ملف .session بجانبه
    export TELEGRAM_TARGET="@your_target_channel"
    python3 collect/16_telegram_upload.py data/mtp_session_2026-10-03.tar.gz \\
        --caption "MTP session artifacts 2026-10-03"
    # أو مجلدًا كاملًا:
    python3 collect/16_telegram_upload.py data/downloads --pattern "*.ar.vtt" --limit 50
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="ملف أو مجلد للرفع")
    ap.add_argument("--caption", default="")
    ap.add_argument("--pattern", default="*", help="نمط عند رفع مجلد")
    ap.add_argument("--limit", type=int, default=0, help="أقصى عدد ملفات (0=الكل)")
    args = ap.parse_args()

    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    target = os.getenv("TELEGRAM_TARGET", "")
    session = os.getenv("TELEGRAM_SESSION", "marathon_session")

    missing = [n for n, v in [("TELEGRAM_API_ID", api_id),
                              ("TELEGRAM_API_HASH", api_hash),
                              ("TELEGRAM_TARGET", target)] if not v]
    if missing:
        print(f"❌ بيانات ناقصة: {missing}\n"
              f"   صدّرها ثم أعد التشغيل. مثال:\n"
              f"   export TELEGRAM_API_ID=... TELEGRAM_API_HASH=... "
              f"TELEGRAM_TARGET=@channel")
        sys.exit(1)

    from telethon import TelegramClient

    p = Path(args.path)
    if p.is_dir():
        files = sorted(p.glob(args.pattern))
        if args.limit:
            files = files[:args.limit]
        if not files:
            print(f"❌ لا ملفات تطابق {args.pattern} في {p}")
            sys.exit(1)
    else:
        files = [p]

    print(f"📤 الهدف: {target} | الملفات: {len(files)}")

    async def run():
        async with TelegramClient(session, api_id, api_hash) as client:
            entity = await client.get_entity(target)
            sent = 0
            for f in files:
                try:
                    await client.send_file(entity, str(f),
                                           caption=args.caption if len(files) == 1
                                           else f"{args.caption} | {f.name}")
                    sent += 1
                    print(f"  ✅ {f.name} ({f.stat().st_size // 1024}KB)")
                except Exception as e:
                    print(f"  ❌ {f.name}: {e}")
            print(f"\n DONE: {sent}/{len(files)}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
