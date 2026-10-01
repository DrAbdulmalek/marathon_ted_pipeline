# src/marathon_runner.py
"""
المنسّق الرئيسي — يربط المراقب والرافع ومعالجات OCR وTED والترجمة
في دورة تشغيل واحدة (run.py).
"""
import logging
import signal
from pathlib import Path
from typing import Optional

import yaml

from .channel_monitor import ChannelMonitor
from .ted_fetcher import TedFetcher
from .telegram_uploader import TelegramUploader

logger = logging.getLogger(__name__)


class MarathonRunner:
    """تشغيل خط الإنتاج الكامل (وضع المراقبة المستمرة)."""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.config_path = config_path
        self.monitor: Optional[ChannelMonitor] = None
        self.uploader: Optional[TelegramUploader] = None
        self._stop = False

    # ---------- مهام فردية ----------
    def process_pdf(self, pdf_path: Path, upload: bool = True) -> dict:
        """معالجة PDF من رابط أو مسار."""
        from .pdf_ocr import PDFOCRProcessor

        result = PDFOCRProcessor(
            rules_file=self.config.get("ocr", {}).get(
                "rules_file", "config/marathon_ocr_rules.yaml"
            ),
            output_dir=Path(
                self.config.get("storage", {}).get("download_dir", "data/downloads")
            )
            / "pdf",
        ).process_and_save(pdf_path)

        if upload and self.uploader:
            stem_dir = Path(pdf_path).stem
            self.uploader.upload_results(
                Path(self.config["storage"]["download_dir"]) / "pdf" / stem_dir,
                title=result["metadata"].get("source_file", str(pdf_path.name)),
            )
        return result

    def process_epub(self, epub_path: Path, upload: bool = True) -> dict:
        """معالجة EPUB."""
        from .epub_ocr import EpubOCRProcessor

        result = EpubOCRProcessor(
            rules_file=self.config.get("ocr", {}).get(
                "rules_file", "config/marathon_ocr_rules.yaml"
            ),
            output_dir=Path(
                self.config.get("storage", {}).get("download_dir", "data/downloads")
            )
            / "epub",
        ).process_and_save(epub_path)

        if upload and self.uploader:
            self.uploader.upload_results(
                Path(self.config["storage"]["download_dir"])
                / "epub"
                / Path(epub_path).stem,
                title=result["metadata"].get("source_file", str(epub_path.name)),
            )
        return result

    def process_ted(self, ted_url: str, translate: bool = True) -> dict:
        """جلب محادثة TED ونشرها."""
        fetcher = TedFetcher(self.config)
        transcript = fetcher.fetch(ted_url)
        if not transcript:
            return {"ok": False, "error": "فشل الجلب"}
        out = {
            "ok": True,
            "talk_id": transcript.talk_id,
            "title": transcript.title,
            "source_text": transcript.source_text,
            "target_text": transcript.target_text,
        }
        if translate and not transcript.target_text and self.uploader:
            from .translator import Translator

            t = Translator(engine="google")
            res = t.translate(transcript.source_text, src="en", tgt="ar")
            out["auto_translation"] = res.translated_text
        if self.uploader:
            body = out.get("target_text") or out.get("auto_translation", "")
            self.uploader.send_message(f"🎬 {transcript.title}\n\n{body}")
        return out

    # ---------- التشغيل ----------
    def start(self) -> None:
        """تشغيل المراقبة المستمرة (يُوقف بـ SIGINT/SIGTERM)."""
        self.uploader = TelegramUploader(self.config)
        self.monitor = ChannelMonitor(config_path=self.config_path)

        def _handle(signum, frame):
            logger.info("إشارة إيقاف %s — إنهاء نظيف", signum)
            self._stop = True
            self.monitor.stop()

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        logger.info("🚀 Marathon Runner يبدأ...")
        self.monitor.run()

    def health(self) -> dict:
        """فحص صحة سريع للمكوّنات."""
        return {
            "config_loaded": bool(self.config),
            "monitor_running": bool(self.monitor and self.monitor.running),
            "target_channel": self.config.get("telegram", {}).get(
                "target_channel", ""
            ),
        }
