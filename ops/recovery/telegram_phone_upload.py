#!/usr/bin/env python3
"""Telegram login + delivery — recovery version (credentials from env only).

Login flow : phone file -> send_code_request -> wait code file -> sign_in
2FA        : wait password file if SessionPasswordNeededError
Delivery   : intro text + files-that-exist to TELEGRAM_TARGET, fallback "me".

Env:
  TELEGRAM_API_ID / TELEGRAM_API_HASH (required)
  TELEGRAM_TARGET  (required channel username, no @)
  TELEGRAM_SESSION (optional, default ./mtp_upload)
  TG_PHONE_FILE / TG_CODE_FILE / TG_PW_FILE (optional, default beside script)

Notes (telethon 1.45):
- phone_code_hash lives only in memory per client run; a code without a live
  send_code_request is useless -> always go through this script fresh.
- qr.recreate() returns None in 1.45 (phone flow only here).
- code file is cleared at start; stale codes from previous runs are rejected.
"""
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TARGET = os.environ.get("TELEGRAM_TARGET", "")

BASE = Path(__file__).resolve().parent
SESSION = os.environ.get("TELEGRAM_SESSION", str(BASE / "mtp_upload"))
PHONE_FILE = Path(os.environ.get("TG_PHONE_FILE", str(BASE / "tg_phone.txt")))
CODE_FILE = Path(os.environ.get("TG_CODE_FILE", str(BASE / "tg_code.txt")))
PW_FILE = Path(os.environ.get("TG_PW_FILE", str(BASE / "tg_password.txt")))
STATE = BASE / "telegram_state.json"
DL = Path(os.environ.get("MTP_DOWNLOAD_DIR", str(BASE.parent / "download")))

if not (API_ID and API_HASH and TARGET):
    sys.exit("FATAL: export TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_TARGET")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def update_state(**kw):
    try:
        st = json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception:
        st = {}
    st.update(kw)
    st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2))


async def wait_file(path: Path, minutes: int):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        if path.exists():
            t = path.read_text().strip()
            if t:
                return t
        await asyncio.sleep(3)
    return None


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_session_tar():
    sess = Path(SESSION + ".session")
    if not sess.exists():
        return None
    try:
        tmp_copy = BASE / "mtp_upload_copy.session"
        shutil.copy2(sess, tmp_copy)
        out = DL / "mtp_session.tar.gz"
        with tarfile.open(out, "w:gz") as tf:
            tf.add(tmp_copy, arcname="mtp_upload.session")
        tmp_copy.unlink(missing_ok=True)
        log(f"session archive built: {out} ({out.stat().st_size} bytes)")
        return out
    except Exception as e:
        log(f"session tar failed: {e}")
        return None


async def deliver(client):
    files = []
    for p in sorted(DL.glob("*.tar.gz")) + sorted(DL.glob("CORPUS_STATS.json")):
        files.append((p.name, p))

    intro = (
        "📦 تسليم MTP (marathon_ted_pipeline)\n"
        f"التاريخ: {time.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"عدد الملفات المرفقة: {len(files)}\n"
    )
    for tgt in (TARGET, "me"):
        try:
            ent = await client.get_entity(tgt)
            await client.send_message(ent, intro)
            delivered = []
            for name, p in files:
                cap = f"{name}\nsha256: {sha256(p)}"
                await client.send_file(ent, p, caption=cap,
                                       force_document=True)
                delivered.append(name)
                log(f"delivered {name} -> {tgt}")
            update_state(delivered_to=str(tgt), delivered=delivered)
            return str(tgt)
        except (ChannelPrivateError, ChatWriteForbiddenError, ValueError) as e:
            log(f"target {tgt} failed ({type(e).__name__}) -> fallback")
        except Exception as e:
            log(f"deliver to {tgt} error: {type(e).__name__}: {e}")
    update_state(delivery="FAILED")
    return None


async def main():
    phone = PHONE_FILE.read_text().strip() if PHONE_FILE.exists() else ""
    if not phone:
        sys.exit(f"FATAL: no phone in {PHONE_FILE}")

    CODE_FILE.write_text("")  # clear stale codes
    update_state(phase="CONNECTING", phone=phone)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        sent = None
        for req in range(1, 4):
            try:
                sent = await client.send_code_request(phone)
                break
            except FloodWaitError as e:
                log(f"FloodWait {e.seconds}s on send_code_request (try {req}/3)")
                update_state(phase="FLOODWAIT", flood_wait_seconds=e.seconds)
                await asyncio.sleep(e.seconds + 3)
        if sent is None:
            update_state(phase="CODE_SEND_FAILED")
            sys.exit("FATAL: could not send code after retries")
        log(f"CODE SENT to {phone}")
        update_state(phase="CODE_SENT", phone=phone)

        ok = False
        for attempt in range(1, 6):
            log(f"waiting for code (attempt {attempt}/5, window 60 min)")
            code = await wait_file(CODE_FILE, 60)
            if not code:
                log("no code arrived within window")
                break
            code = code.replace(" ", "").replace("-", "")
            try:
                await client.sign_in(phone=phone, code=code)
                ok = True
                break
            except SessionPasswordNeededError:
                log("2FA required - waiting password file (30 min)")
                pw = await wait_file(PW_FILE, 30)
                if pw:
                    await client.sign_in(password=pw)
                    ok = True
                break
            except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                log(f"code rejected (attempt {attempt}) - cleared, wait next")
                CODE_FILE.write_text("")
            except FloodWaitError as e:
                log(f"FloodWait {e.seconds}s on sign_in - sleeping")
                await asyncio.sleep(e.seconds + 3)

        if not ok:
            update_state(phase="AUTH_FAILED")
            sys.exit("FATAL: auth failed")

    me = await client.get_me()
    log(f"AUTHORIZED as {me.first_name} (id={me.id}, username={me.username})")
    update_state(phase="AUTHORIZED", tg_id=me.id, username=me.username)

    tgt = await deliver(client)
    log(f"DELIVERY DONE -> {tgt}")
    update_state(phase="COMPLETE", delivered_to=tgt)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
