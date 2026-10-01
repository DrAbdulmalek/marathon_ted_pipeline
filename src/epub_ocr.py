# src/epub_ocr.py
"""
معالج EPUB: فك الأرشيف → استخراج نص الفصول (ebooklib + html) →
قواعد OCR الـ 18 → Markdown + بيانات تعريف، مع فصل صحيح/خاطئ.
الفصول التي تحتاج OCR فعلي (صور ممسوحة) تمر عبر محرك tesseract.
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .ocr_processor import OCRProcessor

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS = re.compile(r"</(p|div|h[1-6]|li|tr)>", re.I)


class EpubOCRProcessor:
    """معالجة EPUB: نصوص رقمية مباشرة، وصور ممسوحة عبر OCR."""

    def __init__(
        self,
        rules_file: Optional[str] = None,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
    ):
        self.rules_file = rules_file or "config/marathon_ocr_rules.yaml"
        self.output_dir = Path(output_dir or "data/downloads/epub")
        self.proc = OCRProcessor(rules_file=self.rules_file)
        self.language = language or self.proc.settings.get("language", "ara+eng")

    # ---------- استخراج ----------
    def _extract_html_text(self, raw: bytes) -> str:
        html = raw.decode("utf-8", errors="ignore")
        html = _BLOCK_TAGS.sub("\n", html)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        text = _TAG_RE.sub("", html)
        return text

    def _ocr_chapter_images(self, book, chapter) -> str:
        """OCR للصور داخل الفصل (كتب ممسوحة ضوئيًا)."""
        import io

        import pytesseract
        from PIL import Image

        texts = []
        try:
            for item in book.get_items_of_type(9):  # EpubImage
                img = Image.open(io.BytesIO(item.get_content()))
                text = pytesseract.image_to_string(img, lang=self.language)
                if text.strip():
                    texts.append(text.strip())
        except Exception as exc:  # لا صور أو فشل OCR — نتجاهل بلطف
            logger.debug("OCR للصور تخطّي: %s", exc)
        return "\n\n".join(texts)

    # ---------- المعالجة ----------
    def process(self, epub_path: Path) -> dict:
        """معالجة EPUB كاملًا وإرجاع markdown + metadata.

        الواجهة المستخدمة من queue_worker:
            result = proc.process(Path(epub_path))
            result["markdown"], result["metadata"]
        """
        import ebooklib
        from ebooklib import epub

        epub_path = Path(epub_path)
        if not epub_path.exists():
            raise FileNotFoundError(f"الملف غير موجود: {epub_path}")

        logger.info("معالجة EPUB: %s", epub_path.name)
        book = epub.read_epub(str(epub_path))

        chapters = []
        confidences = []
        ocr_used = False
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            text = self._extract_html_text(item.get_content())
            if len(text.strip()) < 40:
                # فصل شبه فارغ — جرّب OCR على صور الفصل
                ocr_text = self._ocr_chapter_images(book, item)
                if ocr_text.strip():
                    ocr_used = True
                    text = ocr_text
                    confidences.append(0.75)  # ثقة افتراضية للـ OCR
            if text.strip():
                chapters.append(text.strip())

        raw_text = "\n\n".join(chapters)
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 1.0

        result = self.proc.process_text(raw_text, confidence=avg_conf)
        result["metadata"].update({
            "source_file": epub_path.name,
            "source_type": "epub",
            "chapters": len(chapters),
            "ocr_used": ocr_used,
            "ocr_language": self.language,
            "avg_confidence": round(avg_conf, 4),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    def process_and_save(self, epub_path: Path) -> dict:
        """معالجة + كتابة المخرجات في output_dir/<stem>/."""
        epub_path = Path(epub_path)
        result = self.process(epub_path)
        out_dir = self.output_dir / epub_path.stem
        paths = self.proc.save_outputs(result, out_dir, epub_path.stem)
        result["paths"] = {k: str(v) if v else None for k, v in paths.items()}
        return result
