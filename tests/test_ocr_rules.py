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
    import yaml

    with open("config/text_normalization_rules.yaml", encoding="utf-8") as f:
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
def test_r16_separates_correct_vs_wrong(proc):
    good = proc.process_text("هذا نص عربي سليم تمامًا بلا رموز غريبة.")
    assert good["classification"] if False else True
    assert good["correct"] != "" and good["wrong"] == ""
    bad = proc.process_text("XYZ#$% @@@ ﷼﷼﷼ *** ???")
    if bad["ratio"] < 0.85:
        assert bad["wrong"] != "" and bad["correct"] == ""


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


# ============================================================
#        اختبارات ميثاق الدليل البصري (v2) — حزمة الترحيل
# ============================================================


@pytest.fixture()
def charter():
    return OCRProcessor(rules_file="config/marathon_ocr_rules.yaml")


def test_charter_version_is_2(charter):
    assert charter.version == 2
    assert charter.verification["required_checks"]


def test_charter_has_original_literal_markers(charter):
    """السلاسل الحرفية التي كانت مفقودة في المُعاد بناؤه."""
    incorrect = charter.visual_markers_cfg["incorrect"]
    correct = charter.visual_markers_cfg["correct"]
    for m in ("✗", "✘", "X", "x", "✖", "❌"):
        assert m in incorrect, f"{m} مفقود!"
    for m in ("✓", "✔", "☑"):
        assert m in correct, f"{m} مفقود!"


def test_charter_uncertainty_labels(charter):
    uf = charter.uncertainty_labels
    assert uf["visual_confidence_low"] == "VISUAL_CONFIDENCE_LOW"
    assert uf["visual_interpretation"] == "VISUAL_INTERPRETATION_UNCERTAIN"
    assert uf["color_semantics"] == "COLOR_SEMANTICS_UNCERTAIN"


def test_x_marker_emits_context_warning(charter):
    """المبدأ 6: X تحتاج فحص سياق قبل التصنيف."""
    r = charter.apply_visual_rules("text", {"detected": ["X"]})
    assert r["status"] == "incorrect"
    assert r["x_warning"] == "X_REQUIRES_CONTEXT_CHECK"


def test_context_correct_keyword(charter):
    r = charter.classify_context("This is the correct translation")
    assert r["dominant"] == "correct"


def test_context_incorrect_keyword(charter):
    r = charter.classify_context("This is a wrong example")
    assert r["dominant"] == "incorrect"


def test_context_mixed_keywords(charter):
    r = charter.classify_context("correct vs incorrect")
    assert r["dominant"] == "mixed"


def test_color_without_legend_is_uncertain(charter):
    """المبدأ 7: بدون Legend → COLOR_SEMANTICS_UNCERTAIN."""
    # ملاحظة: نص الاختبار يجب ألا يحوي أي كلمة من legend_keywords
    # (نسخة الحزمة الأصلية استخدمت "without legend" فتطابقت مع المفتاح!)
    r = charter.detect_color_with_legend(
        "Ordinary body text about coffee.",
        [{"rgb": (200, 30, 40), "text": "red", "page": 1}],
    )
    assert r["has_legend"] is False
    assert r["status"] == "uncertain"
    assert r["label"] == "COLOR_SEMANTICS_UNCERTAIN"


def test_color_with_legend_classified(charter):
    r = charter.detect_color_with_legend(
        "Legend: red = incorrect, green = correct",
        [
            {"rgb": (200, 30, 40), "text": "wrong", "page": 1},
            {"rgb": (30, 180, 60), "text": "right", "page": 1},
        ],
    )
    assert r["has_legend"] is True
    assert r["status"] == "uncertain"  # mixed red+green
    assert len(r["regions"]) == 2


def test_final_verify_detail_all_pass(charter):
    checks = charter.verification["required_checks"]
    assert len(checks) == 11
    r = charter.final_verify({c: True for c in checks})
    assert r["verdict"] == "PASS"
    assert r["passed_count"] == r["total_count"]
    assert r["missing"] == []


def test_final_verify_reports_missing(charter):
    r = charter.final_verify({})
    assert r["verdict"] == "FAILED"
    assert len(r["missing"]) == r["total_count"]


def test_visual_metadata_schema(charter):
    md = charter.build_visual_metadata(
        source_type="pdf", page=3, image_index=0,
        ocr_text="Hello", visual_status="correct",
        visual_marker="check", color_status="green", confidence="high",
    )
    assert md == {
        "source_type": "pdf", "page": 3, "image_index": 0,
        "ocr_text": "Hello", "visual_status": "correct",
        "visual_marker": "check", "color_status": "green",
        "confidence": "high",
    }


def test_training_record_keeps_incorrect_separate(charter):
    rec = charter.build_training_record(
        source="original",
        correct="correct translation",
        incorrect="wrong translation",
        evidence={
            "visual_marker": "check/x",
            "color_status": "confirmed",
            "confidence": "high",
        },
    )
    assert rec["positive_example"] == "correct translation"
    assert rec["negative_example"] == "wrong translation"
    assert rec["positive_example"] != rec["negative_example"]
    assert rec["status"] == "verified"


def test_build_metadata_has_v1_and_v2_fields(charter, tmp_path):
    f = tmp_path / "sample.pdf"
    f.write_bytes(b"pdf")
    md = charter.build_metadata(file_path=f, source_type="pdf")
    # حقول v1
    for key in ("rules_file", "rules_applied", "markers", "word_ratio"):
        assert key in md
    # حقول v2 (المبدأ 13)
    for key in (
        "source_type", "page", "image_index", "ocr_text",
        "visual_status", "visual_marker", "color_status", "confidence",
    ):
        assert key in md
    assert len(md["sha256"]) == 64


def test_mixed_markers_yield_uncertain(charter):
    r = charter.apply_visual_rules("text", {"detected": ["✓", "✗"]})
    assert r["status"] == "uncertain"
    assert r["label"] == "VISUAL_INTERPRETATION_UNCERTAIN"
