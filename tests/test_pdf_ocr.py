# tests/test_pdf_ocr.py
"""اختبارات معالج PDF — البنية والحفظ (بلا مكتبات ثقيلة)."""
from pathlib import Path

import pytest

from src.pdf_ocr import PDFOCRProcessor


def test_processor_init_defaults():
    proc = PDFOCRProcessor(rules_file="config/marathon_ocr_rules.yaml")
    assert proc.dpi == 300
    assert proc.language == "ara+eng"
    assert proc.proc is not None


def test_processor_init_custom(tmp_path):
    proc = PDFOCRProcessor(
        rules_file="config/marathon_ocr_rules.yaml",
        output_dir=tmp_path,
        dpi=200,
        language="eng",
    )
    assert proc.dpi == 200
    assert proc.language == "eng"
    assert proc.output_dir == tmp_path


def test_process_missing_file_raises(tmp_path):
    proc = PDFOCRProcessor(rules_file="config/marathon_ocr_rules.yaml")
    with pytest.raises(FileNotFoundError):
        proc.process(tmp_path / "missing.pdf")


def test_process_and_save_with_mocked_ocr(tmp_path):
    """محاكاة OCR: نص جاهز → قواعد 18 → ملفات md + meta."""
    proc = PDFOCRProcessor(
        rules_file="config/marathon_ocr_rules.yaml",
        output_dir=tmp_path,
    )
    fake_result = {
        "markdown": "نص تجريبي نظيف ومكتوب بشكل سليم وجيد.",
        "correct": "نص تجريبي نظيف ومكتوب بشكل سليم وجيد.",
        "wrong": "",
        "ratio": 1.0,
        "metadata": {
            "rules_applied": ["R01"],
            "markers": [],
            "uncertain_flags": 0,
            "footnotes_count": 0,
            "word_ratio": 1.0,
            "classification": "correct",
        },
    }
    proc.process = lambda pdf_path: fake_result  # نوع استبدال للاختبار

    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    out = proc.process_and_save(pdf)
    stem_dir = tmp_path / "sample"
    assert (stem_dir / "sample.md").exists()
    assert (stem_dir / "sample.meta.json").exists()
    md = (stem_dir / "sample.md").read_text(encoding="utf-8")
    assert "نص تجريبي" in md
    assert out["paths"]["markdown"].endswith("sample.md")


def test_output_paths_use_wrong_suffix(tmp_path):
    """الملف الخاطئ يُحفظ بلاحقة .wrong — فصل صحيح/خاطئ."""
    proc = PDFOCRProcessor(
        rules_file="config/marathon_ocr_rules.yaml",
        output_dir=tmp_path,
    )
    result = proc.proc.process_text("XYZ#$% @@@ ***")
    paths = proc.proc.save_outputs(result, tmp_path, "bad")
    if result["wrong"]:
        assert str(paths["wrong"]).endswith(".wrong.md")
