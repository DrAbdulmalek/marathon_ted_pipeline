"""
Backward-compatibility shim.
المصدر الحقيقي: ocr-core (github.com/DrAbdulmalek/ocr-core)
أي تعديل على قواعد OCR يحدث في ocr-core ثم يُحدَّث الإصدار هنا.
"""
from ocr_core.rules.engine import OCRProcessor, OCRStats  # noqa: F401

__all__ = ["OCRProcessor", "OCRStats"]
