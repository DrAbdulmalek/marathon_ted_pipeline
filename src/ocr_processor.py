# src/ocr_processor.py
"""
محرك قواعد OCR — ينفذ القواعد الـ 18 المعرفة في config/marathon_ocr_rules.yaml
على النص المستخرج من PDF/EPUB، ويفصل المخرجات الصحيحة عن الخاطئة
حتى لا تُدرَّب النماذج على نص مُضلَّل.
"""
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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


@dataclass
class OCRStats:
    """إحصاءات تطبيق القواعد على نص واحد."""
    rules_applied: list = field(default_factory=list)
    markers_found: list = field(default_factory=list)
    uncertain_flags: int = 0
    footnotes: int = 0
    pages_dropped: int = 0


class OCRProcessor:
    """منفّذ القواعد الـ 18 على نص خام قادم من PDF أو EPUB."""

    def __init__(self, rules_file: Optional[str] = None):
        self.rules_file = rules_file or "config/marathon_ocr_rules.yaml"
        with open(self.rules_file, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.rules = {r["id"]: r for r in self.config["rules"]}
        self.settings = self.config.get("settings", {})
        self.stats = OCRStats()

    # ---------- helpers ----------
    def _enabled(self, rule_id: str) -> bool:
        rule = self.rules.get(rule_id, {})
        return rule.get("enabled", False)

    def _apply(self, rule_id: str, text: str, params: Optional[dict] = None) -> str:
        if self._enabled(rule_id):
            self.stats.rules_applied.append(rule_id)
        return text

    # ---------- القواعد ----------
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
        params = self.rules["R08"].get("params", {})
        if params.get("keep_in_metadata"):
            self.stats.diacritics_seen = bool(
                re.search(r"[\u064b-\u0652]", text)
            )
        return re.sub(r"[\u064b-\u0652]", "", text)

    def r09_normalize_arabic_letters(self, text: str) -> str:
        """R09: توحيد الألف/الياء/التاء المربوطة."""
        if not self._enabled("R09"):
            return text
        params = self.rules["R09"].get("params", {})
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
        params = self.rules["R10"].get("params", {})
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
        table = self.rules["R13"].get("params", {}).get("table", {})
        for bad, good in table.items():
            text = text.replace(bad, good)
        return text

    def r14_detect_visual_markers(self, text: str) -> str:
        """R14: كشف الرموز والألوان وعزلها كسِمات بصرية."""
        if not self._enabled("R14"):
            return text
        markers = self.rules["R14"].get("params", {}).get("markers", [])
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
        params = self.rules["R15"].get("params", {})
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

    def classify_visual_evidence(self, markers=None, colors=None, context=None) -> dict:
        """Classify only when the visual evidence itself supports correctness."""
        markers = [str(x).lower() for x in (markers or [])]
        colors = [str(x).lower() for x in (colors or [])]
        context = context or {}
        status = "uncertain"
        if any(x in markers for x in ("✓", "✔", "check", "correct")):
            status = "correct"
        if any(x in markers for x in ("✗", "✘", "x", "cross", "incorrect")):
            status = "incorrect"
        if "green" in colors and "red" not in colors:
            status = "correct"
        elif "red" in colors and "green" not in colors:
            status = "incorrect"
        return {
            "status": status,
            "markers": markers,
            "colors": colors,
            "context": context,
            "confidence": "high" if status != "uncertain" else "low",
        }

    def r16_separate_correct_vs_wrong(self, text: str, visual_evidence: Optional[dict] = None) -> dict:
        """R16: يفصل أمثلة الخطأ عن النص الموثق بصريًا؛ لا يحوّل نظافة OCR إلى حقيقة."""
        visual_evidence = visual_evidence or {}
        status = visual_evidence.get("status", "uncertain")
        ratio = float(visual_evidence.get("word_ratio", 0.0))
        if status == "correct":
            return {"correct": text, "wrong": "", "ratio": round(ratio, 4), "classification": "correct", "classification_basis": "visual_evidence"}
        if status == "incorrect":
            return {"correct": "", "wrong": text, "ratio": round(ratio, 4), "classification": "wrong", "classification_basis": "visual_evidence"}
        return {"correct": "", "wrong": text, "ratio": round(ratio, 4), "classification": "uncertain", "classification_basis": "insufficient_evidence"}

    def r17_detect_lists_and_headings(self, text: str) -> str:
        """R17: كشف العناوين والقوائم وتحويلها لـ Markdown."""
        if not self._enabled("R17"):
            return text
        params = self.rules["R17"].get("params", {})
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

    # ---------- خط الأنابيب الكامل ----------
    def process_text(
        self, raw_text: str, confidence: float = 1.0, visual_evidence: Optional[dict] = None
    ) -> dict:
        """تنفيذ القواعد الـ 18 بالترتيب وإرجاع النص النظيف + البيانات الوصفية.

        Returns:
            {
              "markdown": str,          # النص النهائي الصياغة
              "correct": str,           # نسخة "صحيح" (فارغة إن كان المقطع خاطئًا)
              "wrong": str,             # نسخة "خطأ" (فارغة إن كان المقطع صحيحًا)
              "ratio": float,           # نسبة سلامة الكلمات
              "metadata": dict,         # بيانات تعريف كاملة
              "stats": OCRStats-ish,    # إحصاءات القواعد
            }
        """
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
        sep = self.r16_separate_correct_vs_wrong(text, visual_evidence=visual_evidence)

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
            "classification": sep.get("classification", "uncertain"),
            "classification_basis": sep.get("classification_basis", "insufficient_evidence"),
            "visual_evidence": visual_evidence or {"status": "uncertain", "confidence": "low"},
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
