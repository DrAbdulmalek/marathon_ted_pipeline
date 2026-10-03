# src/ocr_processor.py
"""
محرك قواعد OCR — طبقتان بتوافق خلفي كامل:

  1) محرك التنظيف النصي (v1): القواعد R01–R18 كما هي — تُقرأ الآن من
     config/text_normalization_rules.yaml (أو أي ملف v1 بنية rules: [...]).

  2) ميثاق الدليل البصري (v2): يُقرأ من config/marathon_ocr_rules.yaml
     (version: 2 — visual_markers / color_semantics / uncertainty_flags /
     classification_labels / training_data_rules / final_verification).

عند تحميل ملف v2 يكتشف المُحسِّنُ الإصدارَ ويحمّل قواعد التنظيف تلقائيًا من
ملف التطبيع الملازم، فتبقى كل واجهات v1 تعمل دون تعديل المستهلكين
(pdf_ocr / epub_ocr / marathon_runner / channel_monitor / api / bot).

Public API المحفوظ (v1 — لا يتغير):
  - sha256(path) -> str
  - build_metadata(...) -> dict        [محسّن: حقول v1 + حقول v2]
  - apply_visual_rules(text, markers) -> dict   [+ حقل x_warning]
  - verify_output(result) -> "PASS"|"PARTIAL"|"UNCERTAIN"|"FAILED"
  - build_training_record(source, correct, incorrect, evidence) -> dict
  - process_text(raw_text, confidence) -> dict
  - save_outputs(result, out_dir, stem) -> dict
  - r01..r18 (طرق القواعد الـ 18) + OCRStats

Public API الجديد (v2):
  - classify_context(text) -> dict
  - detect_color_with_legend(text, colors) -> dict
  - build_visual_metadata(**kw) -> dict
  - final_verify(result) -> dict   (verdict + تفصيل كل فحص)
"""
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# أنماط مشتركة
_CONTROL_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\ufeff]")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")
_DIGITS_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PUNCT_MAP = str.maketrans({
    "،": "،", "‚": ",", "„": '"', "“": '"', "”": '"',
    "‘": "'", "’": "'", "«": '"', "»": '"',
    "؟": "؟", "؛": "؛", "…": "...",
})
_HYPHEN_END_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
MIN_CONTINUATION_WORDS = 7   # حد اعتبار السطر نصًا جاريًا قابلًا للدمج
_FOOTNOTE_RE = re.compile(r"^\s*([¹²³⁴⁵⁶⁷⁸⁹]|\d{1,2}|\(\d{1,2}\)|\[\d{1,2}\])\s+")
_SENTENCE_END = re.compile(r"[.!؟?…:؛]\"?\s*$")

# ---------- ثوابت v2 الافتراضية (fallback) ----------
_DEFAULT_CORRECT = ["✓", "✔", "☑"]
_DEFAULT_INCORRECT = ["✗", "✘", "X", "x", "✖", "❌"]
_DEFAULT_UNCERTAINTY = {
    "visual_confidence_low": "VISUAL_CONFIDENCE_LOW",
    "visual_interpretation": "VISUAL_INTERPRETATION_UNCERTAIN",
    "color_semantics": "COLOR_SEMANTICS_UNCERTAIN",
}
_DEFAULT_CHECKS = [
    "tables_preserved",
    "column_order_preserved",
    "images_captured",
    "markers_captured",
    "color_semantics_preserved",
    "correct_incorrect_separated",
    "error_examples_flagged",
    "uncertainty_flagged",
    "no_silent_correction",
    "training_safety_verified",
    "original_reference_traceable",
]
_DEFAULT_CONTEXT = {
    "correct": ["correct", "right", "صحيح", "صواب", "الترجمة الصحيحة"],
    "incorrect": ["incorrect", "wrong", "error", "خطأ", "خاطئ", "الترجمة الخاطئة"],
    "revision": ["correction", "revised", "suggested translation",
                 "التصحيح", "مقترح", "مراجعة"],
}
_DEFAULT_LEGEND_KEYWORDS = [
    "legend", "key", "مفتاح", "دليل",
    "correct:", "incorrect:", "صحيح:", "خاطئ:",
]


@dataclass
class OCRStats:
    """إحصاءات تطبيق القواعد على نص واحد."""
    rules_applied: list = field(default_factory=list)
    markers_found: list = field(default_factory=list)
    uncertain_flags: int = 0
    footnotes: int = 0
    pages_dropped: int = 0


class OCRProcessor:
    """محرك قواعد OCR + الدليل البصري (v1 تنظيف / v2 ميثاق — توافق خلفي كامل)."""

    def __init__(
        self,
        rules_file: str | None = None,
        normalization_file: str | None = None,
    ):
        self.rules_file = rules_file or "config/marathon_ocr_rules.yaml"
        with open(self.rules_file, encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}

        self.version = self.config.get("version", 1)
        is_v1 = (
            isinstance(self.config.get("rules"), list)
            and not self.config.get("visual_markers")
        )

        if is_v1:
            # ---------- مسار v1 (سلوك سابق حرفيًا) ----------
            self.rules = {r["id"]: r for r in self.config["rules"]}
            self.settings = self.config.get("settings", {})
            self._build_v2_structures_from_v1()
        else:
            # ---------- مسار v2 (ميثاق الدليل البصري) ----------
            self.rules = {}
            self.settings = self.config.get("settings", {})
            self._build_v2_structures_from_charter()
            # تحميل قواعد التنظيف تلقائيًا من ملف التطبيع الملازم
            norm = normalization_file or str(
                Path(self.rules_file).parent / "text_normalization_rules.yaml"
            )
            self.normalization_file = norm if Path(norm).exists() else None
            if self.normalization_file:
                with open(self.normalization_file, encoding="utf-8") as f:
                    norm_cfg = yaml.safe_load(f) or {}
                self.rules = {
                    r["id"]: r for r in norm_cfg.get("rules", []) if "id" in r
                }
                logger.info(
                    "قواعد التنظيف (v1) حُمّلت من %s — %d قاعدة",
                    self.normalization_file, len(self.rules),
                )
                # ميثاق v2 → R14: مزامنة الرموز الحرفية الغامضة فقط.
                # E2E الحقيقي (PDF+tesseract) كشف أن R14 كان يقرأ قائمة v1
                # القديمة (بلا ✓✗✘☑) فتصبح عملية process_text عمياء للرموز
                # الجوهرية. الاتحاد لا الاستبدال: رموز v1 التراثية (⚠ ★ †…)
                # تبقى مكتشفة كما كانت، والميثاق يضاف إليها. X/x تُستبعد
                # عمدًا: استبدالها الأعمى يفسد الكلمات (example→e[x]ample)
                # والمبدأ 6 يوجب فحص سياق لها لا عزلًا — تُدار عبر
                # apply_visual_rules بتحذير X_REQUIRES_CONTEXT_CHECK.
                r14 = self.rules.setdefault(
                    "R14", {"id": "R14", "name": "detect_visual_markers",
                            "enabled": True, "params": {}})
                existing = r14.setdefault("params", {}).get("markers") or []
                r14["params"]["markers"] = existing + [
                    m for m in (self.visual_markers_cfg["correct"]
                                + self.visual_markers_cfg["incorrect"])
                    if m not in ("X", "x") and m not in existing
                ]

        self._build_visual_markers_index()
        self.stats = OCRStats()
        logger.info(
            "تم تحميل قواعد OCR (v%s) من %s", self.version, self.rules_file
        )

    # ---------- بناء بُنى v2 ----------
    def _build_v2_structures_from_charter(self) -> None:
        vm = self.config.get("visual_markers") or {}
        correct = list(vm.get("correct") or _DEFAULT_CORRECT)
        incorrect = list(vm.get("incorrect") or _DEFAULT_INCORRECT)
        # ضمان أن ✗ ✘ X موجودة دائمًا (متطلب صريح من المبدأ 6)
        for m in ("✗", "✘", "X"):
            if m not in incorrect:
                incorrect.append(m)

        uf = self.config.get("uncertainty_flags") or _DEFAULT_UNCERTAINTY
        for k, v in _DEFAULT_UNCERTAINTY.items():
            uf.setdefault(k, v)

        fv = self.config.get("final_verification") or {}
        checks = list(fv.get("checklist") or _DEFAULT_CHECKS)
        verdicts = list(fv.get("verdicts")
                        or ["PASS", "PARTIAL", "UNCERTAIN", "FAILED"])

        color = dict(self.config.get("color_semantics") or {})
        color.setdefault("require_legend", True)
        color.setdefault("legend_keywords", _DEFAULT_LEGEND_KEYWORDS)
        color.setdefault("on_missing_legend", "COLOR_SEMANTICS_UNCERTAIN")

        ctx = (vm.get("context_keywords") or {}) or dict(_DEFAULT_CONTEXT)

        self.visual_markers_cfg = {
            "correct": correct,
            "incorrect": incorrect,
            "caution": vm.get("caution", ""),
        }
        self.uncertainty_labels = uf
        self.classification_labels = self.config.get("classification_labels") or {}
        self.color_semantics = color
        self.verification = {
            "required_checks": checks,
            "final_status_options": verdicts,
        }
        self.training_data_rules = self.config.get("training_data_rules") or {}
        self.context_keywords = ctx

    def _build_v2_structures_from_v1(self) -> None:
        """ملفات v1 القديمة: اشتقاق بُنى v2 من R14 + الافتراضيات."""
        self._build_v2_structures_from_charter()
        r14 = self.rules.get("R14", {}).get("params", {}).get("markers", [])
        if r14:
            vm = self.visual_markers_cfg
            vm["correct"] = [m for m in r14 if m in ("✓", "✔", "☑", "✅")] or vm["correct"]
            vm["incorrect"] = (
                [m for m in r14 if m in ("✖", "✗", "✘", "❌", "X", "x")]
                or vm["incorrect"]
            )
            for m in ("✗", "✘", "X"):
                if m not in vm["incorrect"]:
                    vm["incorrect"].append(m)

    def _build_visual_markers_index(self) -> None:
        vm = self.visual_markers_cfg
        self._correct_set = set(vm["correct"])
        self._incorrect_set = set(vm["incorrect"])

    # ---------- helpers ----------
    def _enabled(self, rule_id: str) -> bool:
        rule = self.rules.get(rule_id, {})
        on = rule.get("enabled", False)
        if on:
            # تتبع صادق للقواعد المطبقة فعليًا (كان _apply معزولة بلا استدعاء)
            if rule_id not in self.stats.rules_applied:
                self.stats.rules_applied.append(rule_id)
        return on

    def _apply(self, rule_id: str, text: str, params: dict | None = None) -> str:
        if self._enabled(rule_id):
            self.stats.rules_applied.append(rule_id)
        return text

    # ---------- القواعد (v1 — كما هي حرفيًا) ----------
    def r01_strip_control_chars(self, text: str) -> str:
        """R01: حذف محارف التحكم غير المرئية."""
        if self._enabled("R01"):
            return _CONTROL_RE.sub("", text)
        return text

    def r02_normalize_unicode_forms(self, text: str) -> str:
        """R02: توحيد أشكال يونيكود NFKC."""
        if self._enabled("R02"):
            return unicodedata.normalize("NFKC", text)
        return text

    def r03_collapse_whitespace(self, text: str) -> str:
        """R03: دمج المسافات المتكررة."""
        if not self._enabled("R03"):
            return text
        text = _WS_RE.sub(" ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def r04_fix_line_hyphenation(self, text: str) -> str:
        """R04: وصل الكلمات المقطوعة بشرطة في نهاية السطر."""
        if self._enabled("R04"):
            return _HYPHEN_END_RE.sub(r"\1\2", text)
        return text

    def r05_merge_broken_paragraphs(self, text: str) -> str:
        """R05: دمج أسطر الفقرة الواحدة (السطر بلا علامة نهاية جملة)."""
        if not self._enabled("R05"):
            return text
        out_lines = []
        buf = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if buf:
                    out_lines.append(buf)
                    buf = ""
                out_lines.append("")
                continue
            # بنود/عناوين/حواشي = أسطر مكتملة لا تُدمج ولا تُلحق بما قبلها
            starts_structural = re.match(
                r"^(?:-|##|\d{1,2}\s|\(\d{1,2}\)|[•▪◦·*])", stripped
            )
            ended = bool(_SENTENCE_END.search(stripped))
            # الدمج فقط مع سطر جارٍ طويل (≥7 كلمات) بلا نهاية جملة
            flowing = (
                buf
                and not starts_structural
                and len(buf.split()) >= MIN_CONTINUATION_WORDS
                and not _SENTENCE_END.search(buf)
            )
            if flowing:
                buf += " " + stripped
            else:
                if buf:
                    out_lines.append(buf)
                buf = stripped
            if ended or starts_structural:
                out_lines.append(buf)
                buf = ""
        if buf:
            out_lines.append(buf)
        return "\n".join(out_lines)

    def r06_remove_page_numbers(self, text: str) -> str:
        """R06: حذف أرقام الصفحات المعزولة."""
        if not self._enabled("R06"):
            return text
        kept = []
        dropped = 0
        for line in text.splitlines():
            if _PAGE_NUM_RE.match(line):
                dropped += 1
                continue
            kept.append(line)
        self.stats.pages_dropped += dropped
        return "\n".join(kept)

    def r07_remove_headers_footers(self, text: str) -> str:
        """R07: حذف الترويسات/التذييلات المتكررة."""
        if not self._enabled("R07"):
            return text
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < 6:
            return text
        first, last = lines[0], lines[-1]
        repeats = sum(1 for ln in lines if ln == first)
        if repeats >= 3 and len(first) < 80:
            lines = [ln for ln in lines if ln != first]
        repeats = sum(1 for ln in lines if ln == last)
        if repeats >= 3 and len(last) < 80:
            lines = [ln for ln in lines if ln != last]
        return "\n".join(lines)

    def r08_strip_diacritics(self, text: str) -> str:
        """R08: حذف التشكيل مع حفظه في بيانات التعريف."""
        if not self._enabled("R08"):
            return text
        params = self.rules.get("R08", {}).get("params", {})
        if params.get("keep_in_metadata"):
            self.stats.diacritics_seen = bool(
                re.search(r"[\u064b-\u0652]", text)
            )
        return re.sub(r"[\u064b-\u0652]", "", text)

    def r09_normalize_arabic_letters(self, text: str) -> str:
        """R09: توحيد الألف/الياء/التاء المربوطة."""
        if not self._enabled("R09"):
            return text
        params = self.rules.get("R09", {}).get("params", {})
        if params.get("alef_variants"):
            text = re.sub("[\u0623\u0625\u0622]", "\u0627", text)
        if params.get("ya_maqsura"):
            text = text.replace("\u0649", "\u064a")
        if params.get("ta_marbuta"):
            text = text.replace("\u0629", "\u0647")
        return text

    def r10_normalize_digits(self, text: str) -> str:
        """R10: توحيد الأرقام العربية-الهندية إلى لاتينية."""
        if not self._enabled("R10"):
            return text
        params = self.rules.get("R10", {}).get("params", {})
        if params.get("keep_original"):
            self.stats.original_digits = bool(re.search(r"[٠-٩]", text))
        return text.translate(_DIGITS_AR)

    def r11_normalize_punctuation(self, text: str) -> str:
        """R11: توحيد علامات الترقيم."""
        if self._enabled("R11"):
            return text.translate(_PUNCT_MAP)
        return text

    def r12_normalize_quotes(self, text: str) -> str:
        """R12: توحيد علامات الاقتباس."""
        if not self._enabled("R12"):
            return text
        text = re.sub(r"[«»“”]", '"', text)
        text = re.sub(r"[‘’]", "'", text)
        return text

    def r13_common_ocr_substitutions(self, text: str) -> str:
        """R13: جدول أخطاء OCR الشائعة (أشكال اللام-ألف المفككة)."""
        if not self._enabled("R13"):
            return text
        table = self.rules.get("R13", {}).get("params", {}).get("table", {})
        for bad, good in table.items():
            text = text.replace(bad, good)
        return text

    def r14_detect_visual_markers(self, text: str) -> str:
        """R14: كشف الرموز والألوان وعزلها كسِمات بصرية."""
        if not self._enabled("R14"):
            return text
        markers = self.rules.get("R14", {}).get("params", {}).get("markers", [])
        found = [m for m in markers if m in text]
        if found:
            self.stats.markers_found = sorted(
                set(self.stats.markers_found) | set(found)
            )
            for m in found:
                text = text.replace(m, f"[{m}]")
        return text

    def r15_flag_uncertain_words(self, text: str, confidence: float = 1.0) -> str:
        """R15: وسم الكلمات منخفضة الثقة بعلامة [؟؟]."""
        if not self._enabled("R15"):
            return text
        params = self.rules.get("R15", {}).get("params", {})
        threshold = params.get("confidence_threshold", 0.80)
        marker = params.get("marker", "[؟؟]")
        min_len = params.get("min_word_length", 2)
        if confidence >= threshold:
            return text
        def _flag(match: re.Match) -> str:
            word = match.group(0)
            if len(word) >= min_len and not word.startswith("["):
                self.stats.uncertain_flags += 1
                return f"{word}{marker}"
            return word
        return re.sub(r"\S+", _flag, text)

    def r16_separate_correct_vs_wrong(self, text: str) -> dict:
        """R16: فصل المخرجات الصحيحة عن الخاطئة (حماية بيانات التدريب)."""
        if "R16" in self.rules and self.rules["R16"].get("enabled", False):
            if "R16" not in self.stats.rules_applied:
                self.stats.rules_applied.append("R16")
        params = self.rules.get("R16", {}).get("params", {})
        threshold = params.get("correct_ratio_threshold", 0.85)
        words = text.split()
        if not words:
            return {"correct": "", "wrong": text, "ratio": 0.0}
        # كلمة "سليمة" = حروف عربية/لاتينية/أرقام/ترقيم قياسي فقط
        ok_re = re.compile(r"^[\u0621-\u064aa-zA-Z0-9.,;:!?()\[\]\"'«»،؛؟-]+$")
        good = sum(1 for w in words if ok_re.match(w))
        ratio = good / len(words)
        return {
            "correct": text if ratio >= threshold else "",
            "wrong": "" if ratio >= threshold else text,
            "ratio": round(ratio, 4),
        }

    def r17_detect_lists_and_headings(self, text: str) -> str:
        """R17: كشف العناوين والقوائم وتحويلها لـ Markdown."""
        if not self._enabled("R17"):
            return text
        params = self.rules.get("R17", {}).get("params", {})
        max_words = params.get("heading_max_words", 12)
        out = []
        for line in text.splitlines():
            stripped = line.strip()
            # قائمة نقطية
            if re.match(r"^[•▪◦·*]\s+", stripped):
                out.append("- " + re.sub(r"^[•▪◦·*]\s+", "", stripped))
                continue
            # عنوان: سطر قصير بلا نهاية جملة
            words = stripped.split()
            if (
                words
                and len(words) <= max_words
                and not _SENTENCE_END.search(stripped)
                and not stripped.startswith("#")
                and not stripped.endswith("-")
            ):
                out.append("## " + stripped)
                continue
            out.append(line)
        return "\n".join(out)

    def r18_extract_footnotes_tables(self, text: str) -> dict:
        """R18: عزل الحواشي السفلية والجداول البسيطة."""
        if not self._enabled("R18"):
            return {"body": text, "footnotes": ""}
        body, footnotes = [], []
        for line in text.splitlines():
            if _FOOTNOTE_RE.match(line):
                footnotes.append(line.strip())
            else:
                body.append(line)
        self.stats.footnotes += len(footnotes)
        return {
            "body": "\n".join(body),
            "footnotes": "\n".join(footnotes),
        }

    # ---------- خط الأنابيب الكامل (v1 — كما هو) ----------
    def process_text(
        self, raw_text: str, confidence: float = 1.0
    ) -> dict:
        """تنفيذ القواعد الـ 18 بالترتيب وإرجاع النص النظيف + البيانات الوصفية."""
        self.stats = OCRStats()
        text = raw_text

        # R01-R03: تنظيف أساسي
        text = self.r01_strip_control_chars(text)
        text = self.r02_normalize_unicode_forms(text)

        # R06-R07: حذف أرقام الصفحات والترويسات (قبل عزل الحواشي
        # حتى لا تُعامل أرقام الصفحات كحواشٍ)
        text = self.r06_remove_page_numbers(text)
        text = self.r07_remove_headers_footers(text)

        # R18: عزل الحواشي قبل الدمج
        parts = self.r18_extract_footnotes_tables(text)
        text = parts["body"]
        footnotes = parts["footnotes"]

        # R04-R05: إصلاح البنية
        text = self.r04_fix_line_hyphenation(text)
        text = self.r05_merge_broken_paragraphs(text)

        # R17: عناوين وقوائم (بعد الدمج — الأسطر القصيرة المعزولة مرشّحة عناوين)
        text = self.r17_detect_lists_and_headings(text)

        # R13/R09-R12: الاستبدالات
        text = self.r13_common_ocr_substitutions(text)
        text = self.r09_normalize_arabic_letters(text)
        text = self.r10_normalize_digits(text)
        text = self.r11_normalize_punctuation(text)
        text = self.r12_normalize_quotes(text)

        # R08: التشكيل (بعد الاستبدالات لتقليل الخلط)
        text = self.r08_strip_diacritics(text)

        # R15: وسم الكلمات غير المؤكدة
        text = self.r15_flag_uncertain_words(text, confidence)

        # R14: كشف الرموز والألوان
        text = self.r14_detect_visual_markers(text)

        # R03: تنظيف نهائي للمسافات
        text = self.r03_collapse_whitespace(text)

        # R16: الفصل صحيح/خاطئ
        sep = self.r16_separate_correct_vs_wrong(text)

        if footnotes:
            text = text + "\n\n---\n\n## الحواشي\n\n" + footnotes

        metadata = {
            "rules_file": self.rules_file,
            "rules_applied": self.stats.rules_applied,
            "markers": self.stats.markers_found,
            "uncertain_flags": self.stats.uncertain_flags,
            "footnotes_count": self.stats.footnotes,
            "page_numbers_removed": self.stats.pages_dropped,
            "word_ratio": sep["ratio"],
            "classification": "correct" if sep["correct"] else "wrong",
            "had_diacritics": getattr(self.stats, "diacritics_seen", False),
            "had_arabic_digits": getattr(self.stats, "original_digits", False),
        }

        return {
            "markdown": text,
            "correct": sep["correct"],
            "wrong": sep["wrong"],
            "ratio": sep["ratio"],
            "metadata": metadata,
        }

    def save_outputs(self, result: dict, out_dir: Path, stem: str) -> dict:
        """كتابة المخرجات: الصحيح والخاطئ في ملفين منفصلين + بيانات تعريف."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_cfg = self.settings.get("output", {})

        md_path = None
        if result["correct"]:
            md_path = out_dir / f"{stem}{out_cfg.get('correct_suffix', '')}.md"
            md_path.write_text(result["correct"], encoding="utf-8")
        wrong_path = None
        if result["wrong"]:
            wrong_path = (
                out_dir / f"{stem}{out_cfg.get('wrong_suffix', '.wrong')}.md"
            )
            wrong_path.write_text(result["wrong"], encoding="utf-8")

        meta_path = out_dir / f"{stem}{out_cfg.get('metadata_suffix', '.meta.json')}"
        meta_path.write_text(
            json.dumps(result["metadata"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"markdown": md_path, "wrong": wrong_path, "metadata": meta_path}

    # ============================================================
    #                      طبقة الدليل البصري (v2)
    # ============================================================
    def sha256(self, file_path: Path) -> str:
        """SHA-256 لملف (المبدأ 2: بصمة المصدر الأصلي)."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _classify_marker(self, symbol: str) -> str:
        s = symbol.strip()
        if s in self._correct_set:
            return "check"
        if s in self._incorrect_set:
            return "x"
        return "other"

    def apply_visual_rules(
        self,
        text: str,
        markers: dict[str, Any],
    ) -> dict[str, Any]:
        """
        markers = {"detected": ["✓", "✗", ...]}
        يُرجع: status, correct_markers, incorrect_markers, label, x_warning
        المبدأ 6: X تتطلب فحص سياق — يُعلَم بـ x_warning لا يُكتم.
        """
        detected = markers.get("detected") or []
        found_correct = [m for m in detected if m in self._correct_set]
        found_incorrect = [m for m in detected if m in self._incorrect_set]

        status = "neutral"
        label: str | None = None

        if found_correct and not found_incorrect:
            status = "correct"
        elif found_incorrect and not found_correct:
            status = "incorrect"
        elif found_correct and found_incorrect:
            status = "uncertain"
            label = self.uncertainty_labels["visual_interpretation"]

        # تحذير X (المبدأ 6): قد تكون رمزًا لا علامة تصحيح
        x_warning = None
        if "X" in found_incorrect:
            x_warning = "X_REQUIRES_CONTEXT_CHECK"

        return {
            "status": status,
            "correct_markers": found_correct,
            "incorrect_markers": found_incorrect,
            "label": label,
            "x_warning": x_warning,
        }

    # ---------- السياق النصي (v2 جديد) ----------
    def classify_context(self, text: str) -> dict[str, Any]:
        """كلمات مفتاحية سياقية (صحيح/خطأ/تصحيح) — مساعدة المبادئ 5 و6."""
        low = text.lower()
        kws = self.context_keywords
        hits: dict[str, list[str]] = {k: [] for k in kws}
        for k, words in kws.items():
            for w in words:
                if w.lower() in low:
                    hits[k].append(w)

        dominant = None
        c_hit, i_hit, r_hit = (
            hits.get("correct"), hits.get("incorrect"), hits.get("revision")
        )
        if c_hit and not i_hit:
            dominant = "correct"
        elif i_hit and not c_hit:
            dominant = "incorrect"
        elif c_hit and i_hit:
            dominant = "mixed"
        elif r_hit:
            dominant = "revision"

        return {"dominant": dominant, "hits": hits}

    # ---------- الألوان المشروطة بـ Legend (v2 جديد — المبدأ 7) ----------
    def detect_color_with_legend(
        self,
        text: str,
        colors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        colors = [{"rgb": (r,g,b), "text": "...", "page": int}, ...]
        - إذا غاب Legend → COLOR_SEMANTICS_UNCERTAIN (لا اختلاق قرار).
        - إذا وُجد → تصنيف دلالي بسيط (أحمر=خاطئ، أخضر=صحيح).
        """
        color_rules = self.color_semantics
        has_legend = self._has_legend(text, color_rules["legend_keywords"])

        result: dict[str, Any] = {
            "has_legend": has_legend,
            "regions": [],
            "status": "neutral",
            "label": None,
        }

        for c in colors:
            rgb = tuple(c.get("rgb", (0, 0, 0)))
            semantic = self._classify_color(rgb)
            if not has_legend:
                semantic = "uncertain"
            result["regions"].append({
                "text": c.get("text", ""),
                "rgb": rgb,
                "semantic": semantic,
                "page": c.get("page"),
            })

        if not has_legend and colors:
            result["status"] = "uncertain"
            result["label"] = color_rules["on_missing_legend"]
        elif has_legend:
            greens = sum(1 for r in result["regions"] if r["semantic"] == "green")
            reds = sum(1 for r in result["regions"] if r["semantic"] == "red")
            if greens and not reds:
                result["status"] = "correct"
            elif reds and not greens:
                result["status"] = "incorrect"
            elif greens and reds:
                result["status"] = "uncertain"
                result["label"] = self.uncertainty_labels[
                    "visual_interpretation"
                ]

        return result

    @staticmethod
    def _classify_color(rgb) -> str:
        r, g, b = rgb
        if r > 150 and g < 100 and b < 100:
            return "red"
        if g > 130 and r < 120 and b < 120:
            return "green"
        if r > 180 and g > 150 and b < 100:
            return "yellow"
        return "other"

    @staticmethod
    def _has_legend(text: str, keywords: list[str]) -> bool:
        low = text.lower()
        return any(k.lower() in low for k in keywords)

    # ---------- بناء metadata (v1 + v2) ----------
    def build_metadata(
        self,
        file_path: Path | None = None,
        source_type: str = "unknown",
        **extra: Any,
    ) -> dict[str, Any]:
        """
        يحتفظ بحقول v1 (rules_file, rules_applied, markers, ...)
        ويضيف حقول مخطط الدليل البصري v2 (المبدأ 13).
        """
        rules_list = self.config.get("rules")
        if not isinstance(rules_list, list) and self.rules:
            rules_list = list(self.rules.values())
        rules_ids = (
            [r.get("id") for r in rules_list if isinstance(r, dict)]
            if isinstance(rules_list, list) else []
        )

        base: dict[str, Any] = {
            # حقول v1 (توافق خلفي)
            "rules_file": self.rules_file,
            "rules_applied": rules_ids,
            "markers": [],
            "uncertain_flags": [],
            "footnotes_count": 0,
            "word_ratio": 1.0,
            "classification": "neutral",
            # حقول v2 (الدليل البصري — المبدأ 13)
            "source_type": source_type,
            "page": None,
            "image_index": None,
            "ocr_text": None,
            "visual_status": "neutral",
            "visual_marker": "none",
            "color_status": "uncertain",
            "confidence": "low",
        }

        if file_path is not None:
            p = Path(file_path)
            base["file_name"] = p.name
            if p.exists():
                base["sha256"] = self.sha256(p)

        base.update(extra)
        return base

    def build_visual_metadata(
        self,
        source_type: str,
        page: int | None = None,
        image_index: int | None = None,
        ocr_text: str | None = None,
        visual_status: str = "neutral",
        visual_marker: str = "none",
        color_status: str = "uncertain",
        confidence: str = "low",
    ) -> dict[str, Any]:
        """مخطط الدليل البصري الكامل وفق v2 (المبدأ 13)."""
        return {
            "source_type": source_type,
            "page": page,
            "image_index": image_index,
            "ocr_text": ocr_text,
            "visual_status": visual_status,
            "visual_marker": visual_marker,
            "color_status": color_status,
            "confidence": confidence,
        }

    # ---------- سجل التدريب (المبدأ 15) ----------
    def build_training_record(
        self,
        source: str,
        correct: str,
        incorrect: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """
        القاعدة 15: الترجمة الخاطئة لا تدخل كـ target أبدًا.
        يدعم المفاتيح القديمة (marker/color) والجديدة
        (visual_marker/color_status).
        """
        marker = evidence.get("visual_marker") or evidence.get("marker")
        color = evidence.get("color_status") or evidence.get("color")
        confidence = evidence.get("confidence", "low")

        status = "verified" if confidence == "high" else "uncertain"

        return {
            "source": source,
            "positive_example": correct or None,
            "negative_example": incorrect or None,
            "evidence": {
                "marker": marker or "none",
                "color": color or "uncertain",
                "confidence": confidence,
            },
            "status": status,
            # حقول قديمة للتوافق
            "correct_translation": correct or None,
            "incorrect_translation": incorrect or None,
        }

    # ---------- التحقق النهائي (المبدأ 17) ----------
    def verify_output(self, result: dict[str, Any]) -> str:
        """توافق خلفي: يعيد الحكم كسلسلة فقط."""
        checks = self.verification["required_checks"]
        if not checks:
            return "FAILED"
        passed = sum(1 for c in checks if result.get(c))
        ratio = passed / len(checks)
        if ratio == 1.0:
            return "PASS"
        if ratio >= 0.7:
            return "PARTIAL"
        if ratio >= 0.4:
            return "UNCERTAIN"
        return "FAILED"

    def final_verify(self, result: dict[str, Any]) -> dict[str, Any]:
        """يعيد تفصيلًا كاملًا: verdict + حالة كل فحص + المفقود."""
        checks = self.verification["required_checks"]
        detail = {c: bool(result.get(c, False)) for c in checks}
        missing = [c for c, ok in detail.items() if not ok]
        return {
            "verdict": self.verify_output(result),
            "checks": detail,
            "missing": missing,
            "passed_count": sum(detail.values()),
            "total_count": len(checks),
        }
