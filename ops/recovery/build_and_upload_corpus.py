#!/usr/bin/env python3
"""Wait for slug campaign -> build corpus tar + stats -> upload to channel.

Chain step after collectors/15_slug_campaign.py finishes:
  1. Poll until no 15_slug_campaign.py process is alive (or skip with
     --now if none running).
  2. Count VTTs (en/ar) + sizes in <repo>/data/downloads.
  3. Tar all *.vtt into MTP_DOWNLOAD_DIR/mtp_corpus.tar.gz
  4. Write CORPUS_STATS.json (fresh + original reference numbers).
  5. Reuse the AUTHORIZED Telethon session — no re-login.
     Upload intro + tar + stats to TELEGRAM_TARGET (fallback "me").

Env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_TARGET,
     TELEGRAM_SESSION (optional), MTP_DOWNLOAD_DIR (optional),
     MTP_REPO (optional, default repo root relative to this file).
"""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChatWriteForbiddenError

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TARGET = os.environ.get("TELEGRAM_TARGET", "")

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("MTP_REPO", str(HERE.parent.parent)))
DOWNLOADS = REPO / "data" / "downloads"
DL = Path(os.environ.get("MTP_DOWNLOAD_DIR", str(REPO / "data")))
TAR_PATH = DL / "mtp_corpus.tar.gz"
STATS_PATH = DL / "CORPUS_STATS.json"

# original verified reference (2026-10-03 byte-verified delivery)
ORIG = {"total": 12778, "en": 6423, "ar": 6355, "talks_alive": 6432,
        "talks_total": 7523, "raw_mb": 241.3}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def campaign_alive():
    try:
        out = subprocess.run(["pgrep", "-f", "15_slug_campaign.py"],
                             capture_output=True, text=True)
        return out.returncode == 0 and out.stdout.strip()
    except Exception:
        return False


def count_vtts():
    en = ar = total_size = 0
    for p in DOWNLOADS.glob("*.vtt"):
        total_size += p.stat().st_size
        if p.name.endswith(".ar.vtt"):
            ar += 1
        elif p.name.endswith(".en.vtt"):
            en += 1
    return en, ar, total_size


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_state(**kw):
    st = {}
    try:
        if (HERE / "telegram_state.json").exists():
            st = json.loads((HERE / "telegram_state.json").read_text())
    except Exception:
        pass
    st.update(kw)
    st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (HERE / "telegram_state.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2))


def build_tar():
    vtts = sorted(DOWNLOADS.glob("*.vtt"))
    if not vtts:
        raise RuntimeError("no vtt files found")
    log(f"tarring {len(vtts)} vtt files...")
    with tarfile.open(TAR_PATH, "w:gz") as tf:
        for p in vtts:
            tf.add(p, arcname=p.name)
    log(f"tar built: {TAR_PATH} ({TAR_PATH.stat().st_size/1e6:.1f} MB)")


def build_stats(en, ar, raw_size):
    total = en + ar
    talks_alive = len({p.name.rsplit(".", 2)[0]
                       for p in DOWNLOADS.glob("*.vtt")})
    stats = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fresh": {
            "total_vtt": total, "en": en, "ar": ar,
            "talks_alive": talks_alive,
            "raw_mb": round(raw_size / 1e6, 1),
            "tar_mb": round(TAR_PATH.stat().st_size / 1e6, 1),
        },
        "original_reference": ORIG,
        "talks_total": ORIG["talks_total"],
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    log(f"stats: en={en} ar={ar} total={total} talks_alive={talks_alive}")


async def upload():
    if not (API_ID and API_HASH and TARGET):
        log("credentials missing - tar/stats built but upload skipped")
        update_state(corpus_upload="NO_CREDENTIALS")
        return
    client = TelegramClient(os.environ.get(
        "TELEGRAM_SESSION", str(HERE / "mtp_upload")), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        log("FATAL: session not authorized - cannot upload")
        update_state(corpus_upload="SESSION_NOT_AUTHORIZED")
        return
    me = await client.get_me()
    log(f"session authorized as {me.first_name} (no re-login needed)")

    files = [(p.name, p) for p in (TAR_PATH, STATS_PATH) if p.exists()]
    intro = (
        "📦 الكوربس المُعاد بناؤه — MTP marathon_ted_pipeline\n"
        f"التاريخ: {time.strftime('%Y-%m-%d %H:%M UTC')}\n"
        "جُمع من جديد عبر collectors/15_slug_campaign.py على القائمة "
        "الكاملة (7,523 محادثة).\n"
    )
    for tgt in (TARGET, "me"):
        try:
            ent = await client.get_entity(tgt)
            await client.send_message(ent, intro)
            for name, p in files:
                cap = f"{name}\nsha256: {sha256(p)}"
                await client.send_file(ent, p, caption=cap,
                                       force_document=True)
                log(f"delivered {name} -> {tgt}")
            update_state(corpus_upload="COMPLETE", delivered_to=str(tgt))
            await client.disconnect()
            return
        except (ChannelPrivateError, ChatWriteForbiddenError, ValueError):
            log(f"target {tgt} failed -> fallback")
        except Exception as e:
            log(f"upload to {tgt} error: {type(e).__name__}: {e}")
    update_state(corpus_upload="FAILED")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true",
                    help="skip waiting for the campaign process")
    args = ap.parse_args()

    en, ar, sz = count_vtts()
    log(f"start checkpoint: en={en} ar={ar} raw={sz/1e6:.1f}MB")
    if not args.now:
        log("waiting for slug campaign to finish...")
        while campaign_alive():
            time.sleep(30)
        log("campaign process finished")
        time.sleep(5)
    en, ar, sz = count_vtts()
    update_state(corpus_build="TARRING", fresh_en=en, fresh_ar=ar)
    build_tar()
    build_stats(en, ar, sz)
    log("corpus ready -> uploading")
    asyncio.run(upload())
    log("ALL DONE")


if __name__ == "__main__":
    main()
