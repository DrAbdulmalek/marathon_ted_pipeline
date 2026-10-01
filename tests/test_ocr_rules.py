# tests/test_ocr_rules.py
"""اختبارات محرك قواعد OCR الـ 18 — كل قاعدة لها اختبار مستقل."""
import pytest

from src.ocr_processor import OCRProcessor


@pytest.fixture()
def proc():
    return OCRProcessor(rules_file="config/marathon_ocr_rules.yaml")


# ---------- R01 ----------
def test_r01_strips_control_chars(proc):
    text = "مرحبا\u200b بالعالم\u200e"
    out = proc.process_text(text)["markdown"]
    assert "\u200b" not in out and "\u200e" not in out
    assert "مرحبا" in out


# ---------- R02 ----------
def test_r02_nfkc_normalization(proc):
    text = "ﬁle ﻻ"   # ligature + lama-alef presentation form
    out = proc.process_text(text)["markdown"]
    assert "لا" in out


# ---------- R03 ----------
def test_r03_collapses_whitespace(proc):
    out = proc.process_text("كلمة    كلمة\n\n\n\nسطر")["markdown"]
    assert "  " not in out
    assert out.count("\n\n") <= 1


# ---------- R04 ----------
def test_r04_joins_hyphenated_words(proc):
    out = proc.process_text("inter-\nnational talk")["markdown"]
    assert "international" in out


# ---------- R05 ----------
def test_r05_merges_broken_paragraphs(proc):
    # سطر جارٍ طويل (≥7 كلمات) بلا نهاية جملة + سطر متابعة
    text = (
        "وفي ختام هذا التحليل الطويل والمعمق يمكن القول إن الوضع العام غير مكتمل"
        "\nوتكملته تأتي في السطر التالي من الصفحة.\nجملة جديدة."
    )
    out = proc.process_text(text)["markdown"]
    assert "غير مكتمل وتكملته" in out


# ---------- R06 ----------
def test_r06_removes_page_numbers(proc):
    text = "نص أول\n42\nنص ثانٍ\n\n43"
    out = proc.process_text(text)["markdown"]
    assert "\n42\n" not in out
    assert proc.stats.pages_dropped >= 1


# ---------- R07 ----------
def test_r07_removes_repeated_headers(proc):
    text = "\n".join(
        ["رأس الصفحة المتكرر"] + [f"سطر المحتوى {i}" for i in range(10)]
        + ["رأس الصفحة المتكرر", "رأس الصفحة المتكرر"]
    )
    out = proc.process_text(text)["markdown"]
    assert out.count("رأس الصفحة المتكرر") < 3


# ---------- R08 ----------
def test_r08_strips_diacritics_and_records(proc):
    text = "مُحَمَّد"
    result = proc.process_text(text)
    assert "\u064e" not in result["markdown"]
    assert result["metadata"]["had_diacritics"] is True


# ---------- R09 ----------
def test_r09_normalizes_alef_ya(proc):
    out = proc.process_text("أإآ إلى ى")["markdown"]
    assert "أ" not in out and "إ" not in out and "آ" not in out
    assert "الي" in out


# ---------- R10 ----------
def test_r10_converts_arabic_digits(proc):
    result = proc.process_text("السنة ٢٠٢٥")
    assert "2025" in result["markdown"]
    assert result["metadata"]["had_arabic_digits"] is True


# ---------- R11 ----------
def test_r11_normalizes_punctuation(proc):
    out = proc.process_text("„نص“ «آخر»")["markdown"]
    assert '"' in out


# ---------- R12 ----------
def test_r12_normalizes_quotes(proc):
    out = proc.process_text("«مقولة» و ‘مقولة’")["markdown"]
    assert "«" not in out and "‘" not in out


# ---------- R13 ----------
def test_r13_substitution_table(proc):
    """R13 تعمل على أشكال العرض بمعزل عن R02 (NFKC يحلها أولًا)."""
    import copy
    import yaml

    with open("config/marathon_ocr_rules.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for r in cfg["rules"]:
        if r["id"] in ("R02", "R09"):
            r["enabled"] = False   # عزل R13 عن NFKC وتوحيد الألف
    import tempfile
    fp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(cfg, fp, allow_unicode=True)
    fp.close()

    isolated = OCRProcessor(rules_file=fp.name)
    out = isolated.process_text("ﻻ ﻷ ﻹ")["markdown"]
    assert "لا" in out and "لأ" in out and "لإ" in out


# ---------- R14 ----------
def test_r14_detects_visual_markers(proc):
    result = proc.process_text("تم بنجاح ✔ والتحذير ⚠ هنا")
    assert "✔" in result["metadata"]["markers"]
    assert "⚠" in result["metadata"]["markers"]
    assert "[✔]" in result["markdown"]


# ---------- R15 ----------
def test_r15_flags_uncertain_words(proc):
    result = proc.process_text("كلمة سليمة أخرى", confidence=0.5)
    assert result["metadata"]["uncertain_flags"] >= 1
    assert "[؟؟]" in result["markdown"]
    # ثقة عالية → لا وسم
    result2 = proc.process_text("كلمة سليمة أخرى", confidence=1.0)
    assert result2["metadata"]["uncertain_flags"] == 0


# ---------- R16 ----------
def test_r16_requires_visual_evidence(proc):
    clean = proc.process_text("هذا نص عربي سليم تمامًا بلا رموز غريبة.")
    assert clean["classification"] == "uncertain"
    assert clean["correct"] == ""
    assert clean["wrong"] == clean["markdown"]

    correct = proc.process_text(
        "هذه ترجمة صحيحة",
        visual_evidence={"status": "correct", "markers": ["check"], "confidence": "high"},
    )
    assert correct["classification"] == "correct"
    assert correct["correct"] == correct["markdown"]
    assert correct["wrong"] == ""

    wrong = proc.process_text(
        "هذه ترجمة خاطئة",
        visual_evidence={"status": "incorrect", "markers": ["x"], "confidence": "high"},
    )
    assert wrong["classification"] == "wrong"
    assert wrong["wrong"] == wrong["markdown"]
    assert wrong["correct"] == ""


# ---------- R17 ----------
def test_r17_detects_lists_and_headings(proc):
    text = "• بند أول\n• بند ثانٍ\nعنوان قصير\nوهذه جملة طويلة نسبيًا تنتهي بنقطة."
    out = proc.process_text(text)["markdown"]
    assert "- بند اول" in out   # أول → اول (توحيد R09 بعد R17)
    assert "## عنوان قصير" in out
    # الجملة الطويلة تُترك كما هي (السطر الأخير بلا دمج)


# ---------- R18 ----------
def test_r18_extracts_footnotes(proc):
    text = "نص رئيسي هنا.\n¹ حاشية أولى\nنص آخر.\n(2) حاشية ثانية"
    result = proc.process_text(text)
    assert "الحواشي" in result["markdown"]
    assert result["metadata"]["footnotes_count"] == 2


# ---------- التكامل ----------
def test_full_pipeline_metadata_structure(proc):
    result = proc.process_text("نص تجريبي عام للتحقق من البنية الكاملة.")
    meta = result["metadata"]
    for key in (
        "rules_file", "rules_applied", "markers", "uncertain_flags",
        "footnotes_count", "word_ratio", "classification",
    ):
        assert key in meta


def test_save_outputs_creates_correct_and_wrong_files(proc, tmp_path):
    result = proc.process_text("نص سليم واضح ومنظم بشكل جيد تمامًا.")
    paths = proc.save_outputs(result, tmp_path, "sample")
    assert paths["metadata"].exists()
    if result["correct"]:
        assert paths["markdown"].exists()
    assert paths["wrong"] is None


def test_visual_evidence_classifier_is_uncertain_without_signal(proc):
    result = proc.classify_visual_evidence(markers=[], colors=[])
    assert result["status"] == "uncertain"
    assert result["confidence"] == "low"


def test_visual_evidence_classifier_uses_check_and_x(proc):
    assert proc.classify_visual_evidence(markers=["check"])["status"] == "correct"
    assert proc.classify_visual_evidence(markers=["x"])["status"] == "incorrect"


def test_visual_color_semantics_are_explicit(proc):
    assert proc.classify_visual_evidence(colors=["green"])["status"] == "correct"
    assert proc.classify_visual_evidence(colors=["red"])["status"] == "incorrect"
    assert proc.classify_visual_evidence(colors=[])["status"] == "uncertain"
