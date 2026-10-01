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
_BLOCK_TAGS = re.compile(r"</(p|div|h[1-6]|li)>", re.I)
_TABLE_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


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

        def table_to_markdown(match):
            rows = []
            for row_html in _TABLE_ROW_RE.findall(match.group(0)):
                cells = []
                for cell_html in _CELL_RE.findall(row_html):
                    cell = _TAG_RE.sub("", cell_html)
                    cell = re.sub(r"\s+", " ", cell).strip().replace("|", "\\|")
                    cells.append(cell)
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            if not rows:
                return ""
            width = max(len(_CELL_RE.findall(r)) for r in _TABLE_ROW_RE.findall(match.group(0)))
            if width <= 0:
                return ""
            sep = "| " + " | ".join(["---"] * width) + " |"
            return rows[0] + "\n" + sep + ("\n" + "\n".join(rows[1:]) if len(rows) > 1 else "")

        html = re.sub(r"<table[^>]*>.*?</table>", table_to_markdown, html, flags=re.I | re.S)
        html = _BLOCK_TAGS.sub("\n", html)
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        return _TAG_RE.sub("", html)

    def _ocr_chapter_images(self, book, chapter) -> tuple[str, dict]:
        """OCR للصور داخل الفصل مع حفظ مؤشرات الصحة/الخطأ والألوان عند الإمكان."""
        import io

        import pytesseract
        from PIL import Image

        texts = []
        markers, colors = [], []
        try:
            for item in book.get_items_of_type(9):  # EpubImage
                img = Image.open(io.BytesIO(item.get_content())).convert("RGB")
                data = pytesseract.image_to_data(img, lang=self.language, output_type=pytesseract.Output.DICT)
                words = []
                for i, raw in enumerate(data["text"]):
                    word = raw.strip()
                    if not word:
                        continue
                    words.append(word)
                    low = word.lower()
                    if low in {"x", "✗", "✘", "❌"}:
                        markers.append("x")
                    elif low in {"✓", "✔", "✅"}:
                        markers.append("check")
                    try:
                        left, top = int(data["left"][i]), int(data["top"][i])
                        width, height = int(data["width"][i]), int(data["height"][i])
                        crop = img.crop((left, top, left + width, top + height))
                        pixels = list(crop.getdata())
                        if pixels:
                            total = len(pixels)
                            red = sum(1 for r,g,b in pixels if r > 150 and r > g * 1.35 and r > b * 1.35)
                            green = sum(1 for r,g,b in pixels if g > 120 and g > r * 1.20 and g > b * 1.10)
                            if red / total >= 0.12:
                                colors.append("red")
                            elif green / total >= 0.12:
                                colors.append("green")
                    except Exception:
                        pass
                if words:
                    texts.append(" ".join(words))
        except Exception as exc:
            logger.debug("OCR للصور تخطّي: %s", exc)
        return "\n\n".join(texts), {"markers": sorted(set(markers)), "colors": sorted(set(colors))}

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
        visual_markers, visual_colors = [], []
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

        visual = self.proc.classify_visual_evidence(
            markers=sorted(set(visual_markers)),
            colors=sorted(set(visual_colors)),
            context={"chapters": len(chapters)},
        )
        visual["word_ratio"] = avg_conf
        result = self.proc.process_text(raw_text, confidence=avg_conf, visual_evidence=visual)
        result["metadata"].update({
            "source_file": epub_path.name,
            "tables_preserved_as_markdown": "|" in raw_text and "---" in raw_text,
            "visual_evidence": visual,
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
