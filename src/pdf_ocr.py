# src/pdf_ocr.py
"""
معالج PDF: تحويل الصفحات إلى صور (PyMuPDF) → OCR (tesseract) →
قواعد OCR الـ 18 → Markdown + بيانات تعريف، مع فصل صحيح/خاطئ.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .ocr_processor import OCRProcessor

logger = logging.getLogger(__name__)


class PDFOCRProcessor:
    """معالجة ملفات PDF عبر OCR مع تطبيق قواعد marathon الـ 18."""

    def __init__(
        self,
        rules_file: Optional[str] = None,
        output_dir: Optional[Path] = None,
        dpi: Optional[int] = None,
        language: Optional[str] = None,
    ):
        self.rules_file = rules_file or "config/marathon_ocr_rules.yaml"
        self.output_dir = Path(output_dir or "data/downloads/pdf")
        self.proc = OCRProcessor(rules_file=self.rules_file)
        settings = self.proc.settings
        self.dpi = dpi or settings.get("dpi", 300)
        self.language = language or settings.get("language", "ara+eng")

    # ---------- استخراج ----------
    def _page_image(self, page, zoom: float):
        import fitz  # PyMuPDF

        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix

    def _ocr_image(self, pix) -> tuple[str, float]:
        import io

        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(pix.tobytes("png")))
        data = pytesseract.image_to_data(
            img, lang=self.language, output_type=pytesseract.Output.DICT
        )
        # إعادة بناء الأسطر مع متوسط الثقة
        lines: dict = {}
        n = len(data["text"])
        for i in range(n):
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            word = data["text"][i].strip()
            conf = float(data["conf"][i])
            if word and conf >= 0:
                lines.setdefault(key, []).append((word, conf))
        text_lines, confs = [], []
        for key in sorted(lines):
            words = lines[key]
            text_lines.append(" ".join(w for w, _ in words))
            confs.append(sum(c for _, c in words) / len(words))
        text = "\n".join(text_lines)
        confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return text, confidence

    # ---------- المعالجة ----------
    def process(self, pdf_path: Path) -> dict:
        """معالجة PDF كاملًا وإرجاع markdown + metadata.

        الواجهة المستخدمة من queue_worker:
            result = proc.process(Path(pdf_path))
            result["markdown"], result["metadata"]
        """
        import fitz  # PyMuPDF

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"الملف غير موجود: {pdf_path}")

        logger.info("معالجة PDF: %s", pdf_path.name)
        doc = fitz.open(str(pdf_path))
        zoom = self.dpi / 72.0

        page_texts = []
        confidences = []
        for pno in range(len(doc)):
            page = doc[pno]
            pix = self._page_image(page, zoom)
            text, conf = self._ocr_image(pix)
            if text.strip():
                page_texts.append(text)
                confidences.append(conf)
        doc.close()

        raw_text = "\n\n".join(page_texts)
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

        result = self.proc.process_text(raw_text, confidence=avg_conf)
        result["metadata"].update({
            "source_file": pdf_path.name,
            "source_type": "pdf",
            "pages": len(page_texts),
            "dpi": self.dpi,
            "ocr_language": self.language,
            "avg_confidence": round(avg_conf, 4),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    def process_and_save(self, pdf_path: Path) -> dict:
        """معالجة + كتابة المخرجات في output_dir/<stem>/."""
        pdf_path = Path(pdf_path)
        result = self.process(pdf_path)
        out_dir = self.output_dir / pdf_path.stem
        paths = self.proc.save_outputs(result, out_dir, pdf_path.stem)
        result["paths"] = {k: str(v) if v else None for k, v in paths.items()}
        return result
