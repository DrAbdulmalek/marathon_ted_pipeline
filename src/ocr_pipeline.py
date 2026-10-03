# src/ocr_pipeline.py
"""
خط أنابيب OCR من طبقتين:
  1) تنظيف نصي (pre-pass) — config/text_normalization_rules.yaml (R01–R13)
  2) دليل بصري — config/marathon_ocr_rules.yaml (ميثاق v2)

الطبقة الأولى تُنفّذ عبر OCRProcessor نفسه (قواعد R01–R13 المجرَّبة)،
والطبقة الثانية عبر طرق v2 (apply_visual_rules / detect_color_with_legend /
classify_context) — بلا تكرار للأنماط.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .ocr_processor import OCRProcessor

logger = logging.getLogger(__name__)

# قواعد الفصل/الكشف تنتمي لميثاق الدليل البصري — تُتخطى في الـ pre-pass
_NORM_SKIP = {"R14", "R15", "R16", "R17", "R18"}

# خريطة معرفات القواعد إلى أسماء الطرق في OCRProcessor
_RULE_METHOD_NAMES = {
    "R01": "r01_strip_control_chars",
    "R02": "r02_normalize_unicode_forms",
    "R03": "r03_collapse_whitespace",
    "R04": "r04_fix_line_hyphenation",
    "R05": "r05_merge_broken_paragraphs",
    "R06": "r06_remove_page_numbers",
    "R07": "r07_remove_headers_footers",
    "R08": "r08_strip_diacritics",
    "R09": "r09_normalize_arabic_letters",
    "R10": "r10_normalize_digits",
    "R11": "r11_normalize_punctuation",
    "R12": "r12_normalize_quotes",
    "R13": "r13_common_ocr_substitutions",
}


class OCRPipeline:
    """ينسّق بين طبقة التنظيف النصي وطبقة الدليل البصري."""

    def __init__(
        self,
        rules_file: str = "config/marathon_ocr_rules.yaml",
        normalization_file: str | None = "config/text_normalization_rules.yaml",
    ):
        self.visual = OCRProcessor(rules_file=rules_file)
        self.normalization = None
        if normalization_file and Path(normalization_file).exists():
            self.normalization = OCRProcessor(
                rules_file=normalization_file, normalization_file=None
            )
        elif self.visual.normalization_file:
            # الميثاق حمّل التطبيع تلقائيًا — أعد استخدامه بلا تحميل مزدوج
            self.normalization = self.visual

    # ---------- طبقة التنظيف (pre-pass — R01..R13 فقط) ----------
    def normalize_text(self, text: str) -> str:
        """يطبّق R01–R13 فقط (لا R14–R18 — تلك للدليل البصري)."""
        if self.normalization is None:
            return text
        for rid in sorted(self.normalization.rules):
            if rid in _NORM_SKIP:
                continue
            rule = self.normalization.rules.get(rid, {})
            if not rule.get("enabled", False):
                continue
            try:
                text = self._apply_norm_rule(rid, text)
            except Exception as e:  # noqa: BLE001 — تنظيف لا يوقف الإنتاج
                logger.warning("فشل %s: %s", rid, e)
        return text

    def _apply_norm_rule(self, rid: str, text: str) -> str:
        """تنفيذ قاعدة تنظيف واحدة عبر المحرك الموحّد."""
        method_name = _RULE_METHOD_NAMES.get(rid)
        if not method_name:
            return text
        method = getattr(self.normalization, method_name, None)
        if method is None:
            return text
        return method(text)

    # ---------- المعالجة الكاملة ----------
    def process_text(
        self,
        raw_text: str,
        detected_markers: list[str],
        detected_colors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """تنظيف → دليل بصري → سياق → ألوان (بالعقد العامة الموثقة)."""
        normalized = self.normalize_text(raw_text)
        visual = self.visual.apply_visual_rules(
            normalized, {"detected": detected_markers}
        )
        color = (
            self.visual.detect_color_with_legend(normalized, detected_colors)
            if detected_colors
            else None
        )
        context = self.visual.classify_context(normalized)
        return {
            "normalized_text": normalized,
            "visual": visual,
            "color": color,
            "context": context,
        }

