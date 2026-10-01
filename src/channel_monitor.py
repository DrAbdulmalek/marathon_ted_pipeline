# src/channel_monitor.py
"""
مراقب قناة تيليجرام — يستمع لرسائل القناة المصدر (Telethon MTProto):
- مرفقات PDF/EPUB → معالجة OCR → نتيجة للقناة الهدف
- روابط TED → جلب وترجمة
- نص عادي (عربي/إنجليزي) → ترجمة
"""
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

TED_URL_RE = re.compile(r"https?://(?:www\.)?ted\.com/talks/\S+")


class ChannelMonitor:
    """مراقبة القناة المصدر وتنفيذ المهام الواردة منها."""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.source = self.config.get("telegram", {}).get("source_channel", "")
        self.download_dir = Path(
            self.config.get("storage", {}).get("download_dir", "data/downloads")
        )
        self.rules_file = self.config.get("ocr", {}).get(
            "rules_file", "config/marathon_ocr_rules.yaml"
        )
        self._client = None
        self.running = False

    # ---------- اتصال ----------
    def _get_client(self):
        if self._client is None:
            from telethon import TelegramClient

            api_id = int(os.getenv("TELEGRAM_API_ID", 0))
            api_hash = os.getenv("TELEGRAM_API_HASH", "")
            session = os.getenv("TELEGRAM_SESSION", "marathon_session")
            self._client = TelegramClient(session, api_id, api_hash)
        return self._client

    # ---------- المعالجات ----------
    def handle_document(self, event) -> None:
        """مرفق PDF/EPUB → OCR → رفع النتيجة."""
        from .pdf_ocr import PDFOCRProcessor
        from .epub_ocr import EpubOCRProcessor
        from .telegram_uploader import TelegramUploader

        doc = event.message.document
        attrs = getattr(doc, "attributes", [])
        filename = next(
            (a.file_name for a in attrs if getattr(a, "file_name", None)),
            f"doc_{event.message.id}",
        )
        suffix = Path(filename).suffix.lower()
        if suffix not in (".pdf", ".epub"):
            return

        self.download_dir.mkdir(parents=True, exist_ok=True)
        save_path = self.download_dir / filename
        event.message.download_media(file=str(save_path))
        logger.info("نُزِّل من القناة: %s", filename)

        try:
            if suffix == ".pdf":
                result = PDFOCRProcessor(
                    rules_file=self.rules_file, output_dir=self.download_dir / "pdf"
                ).process_and_save(save_path)
            else:
                result = EpubOCRProcessor(
                    rules_file=self.rules_file, output_dir=self.download_dir / "epub"
                ).process_and_save(save_path)

            uploader = TelegramUploader(self.config)
            title = result["metadata"].get("source_file", filename)
            n = uploader.upload_results(
                self.download_dir / Path(filename).stem, title=title
            )
            logger.info("رُفع %s ملفًا نتيجةً لـ %s", n, filename)
        except Exception as exc:
            logger.exception("فشلت معالجة %s: %s", filename, exc)

    def handle_ted_link(self, event, url: str) -> None:
        """رابط TED → جلب + ترجمة → نشر."""
        from .ted_fetcher import TedFetcher
        from .telegram_uploader import TelegramUploader

        fetcher = TedFetcher(self.config)
        transcript = fetcher.fetch(url)
        if not transcript:
            return
        text = f"🎬 {transcript.title}\n\n{transcript.target_text or transcript.source_text}"
        TelegramUploader(self.config).send_message(text)

    def handle_text(self, event) -> None:
        """نص عادي → ترجمة فورية."""
        from .translator import Translator

        text = (event.message.message or "").strip()
        if not text or TED_URL_RE.search(text):
            return
        if not (2 < len(text) < 4000):
            return
        try:
            t = Translator(engine="google")
            if re.search(r"[\u0600-\u06ff]", text):
                res = t.translate(text, src="ar", tgt="en")
            else:
                res = t.translate(text, src="en", tgt="ar")
            event.reply(res.translated_text)
        except Exception as exc:
            logger.debug("ترجمة نص القناة فشلت: %s", exc)

    # ---------- الحلقة ----------
    async def _run_async(self) -> None:
        from telethon import events

        client = self._get_client()
        await client.start()
        entity = await client.get_entity(self.source)

        @client.on(events.NewMessage(chats=entity))
        async def _on_message(event):
            try:
                if event.message.document:
                    self.handle_document(event)
                elif event.message.message:
                    m = TED_URL_RE.search(event.message.message)
                    if m:
                        self.handle_ted_link(event, m.group(0))
                    else:
                        self.handle_text(event)
            except Exception:
                logger.exception("خطأ في معالجة رسالة القناة")

        self.running = True
        logger.info("👁️ المراقبة بدأت على: %s", self.source)
        await client.run_until_disconnected()

    def run(self) -> None:
        """تشغيل المراقب (حظر كامل)."""
        try:
            asyncio.get_event_loop().run_until_complete(self._run_async())
        except RuntimeError:
            asyncio.run(self._run_async())

    def stop(self) -> None:
        self.running = False
        if self._client:
            asyncio.ensure_future(self._client.disconnect())
