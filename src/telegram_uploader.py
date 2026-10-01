# src/telegram_uploader.py
"""
رافع تيليجرام — نشر النتائج (Markdown/TXT/SRT) إلى قناة الهدف عبر Telethon.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramUploader:
    """رفع ملفات ورسائل إلى قناة تيليجرام الهدف (جلسة مستخدم MTProto)."""

    def __init__(self, config: dict):
        self.config = config
        tg = config.get("telegram", {})
        self.api_id = int(os.getenv("TELEGRAM_API_ID", tg.get("api_id", 0)))
        self.api_hash = os.getenv("TELEGRAM_API_HASH", tg.get("api_hash", ""))
        self.session = os.getenv(
            "TELEGRAM_SESSION", tg.get("session", "marathon_session")
        )
        self.target = tg.get("target_channel", "")
        self._client = None

    # ---------- اتصال ----------
    def _get_client(self):
        if self._client is None:
            from telethon import TelegramClient

            self._client = TelegramClient(
                self.session, self.api_id, self.api_hash
            )
        return self._client

    def connect(self):
        client = self._get_client()
        if not client.is_connected():
            client.start()

    def disconnect(self):
        if self._client and self._client.is_connected():
            self._client.disconnect()

    # ---------- النشر ----------
    async def _send_message_async(self, text: str, parse_mode=None):
        from telethon.tl.types import PEER_CHANNEL

        self.connect()
        client = self._get_client()
        entity = await client.get_entity(self.target)
        await client.send_message(entity, text, parse_mode=parse_mode)

    async def _send_file_async(self, file_path: Path, caption: str = ""):
        self.connect()
        client = self._get_client()
        entity = await client.get_entity(self.target)
        await client.send_file(entity, str(file_path), caption=caption)

    def send_message(self, text: str) -> bool:
        """إرسال رسالة نصية إلى القناة الهدف."""
        try:
            asyncio.get_event_loop().run_until_complete(
                self._send_message_async(text)
            )
            return True
        except RuntimeError:
            return asyncio.run(self._send_message_async(text)) or True
        except Exception as exc:
            logger.error("فشل إرسال رسالة: %s", exc)
            return False

    def send_files(self, paths: list, caption: str = "") -> int:
        """رفع عدة ملفات — يعيد عدد ما رُفع فعليًا."""
        sent = 0
        for p in paths:
            p = Path(p)
            if not p.exists():
                logger.warning("ملف مفقود للرفع: %s", p)
                continue
            try:
                try:
                    asyncio.get_event_loop().run_until_complete(
                        self._send_file_async(p, caption)
                    )
                except RuntimeError:
                    asyncio.run(self._send_file_async(p, caption))
                sent += 1
            except Exception as exc:
                logger.error("فشل رفع %s: %s", p.name, exc)
        return sent

    def upload_results(self, result_dir: Path, title: str = "") -> int:
        """رفع مخرجات معالجة كاملة (md + json) من مجلد النتائج."""
        result_dir = Path(result_dir)
        files = sorted(result_dir.glob("*.md")) + sorted(
            result_dir.glob("*.meta.json")
        )
        return self.send_files(files, caption=title)
