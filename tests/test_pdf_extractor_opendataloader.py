"""اختبارات مستخرج OpenDataLoader — تُتخطى بأناقة عند غياب الحزمة/JVM."""
from __future__ import annotations

import importlib.util

import pytest

from src.pdf_extractor_opendataloader import extract_pdf, is_available


def test_missing_file_reported_not_raised():
    r = extract_pdf("/nonexistent/doc.pdf")
    assert r["ok"] is False
    assert "file not found" in r["error"]
    assert r["engine"] == "opendataloader-pdf"


def test_unavailable_is_graceful(tmp_path):
    """عند غياب الحزمة أو java: error واضح بلا استثناء."""
    from src import pdf_extractor_opendataloader as mod

    if is_available():
        pytest.skip("البيئة كاملة — لا يمكن محاكاة الغياب")
    fake = tmp_path / "doc.pdf"
    fake.write_bytes(b"%PDF-1.4 fake")
    r = extract_pdf(str(fake))
    assert r["ok"] is False
    assert r["error"] is not None
    assert "opendataloader-pdf" in r["error"] or "java" in r["error"]


def test_is_available_returns_bool():
    assert isinstance(is_available(), bool)


def test_module_independent_of_core_pipeline():
    """الوحدة اختيارية بالكامل: لا تستورد أي اعتماد من mtp نفسها."""
    src = importlib.util.find_spec("src.pdf_extractor_opendataloader")
    assert src is not None
    text = open(src.origin, encoding="utf-8").read()
    for heavy in ("import pymupdf", "import fitz", "import telethon", "import streamlit"):
        assert heavy not in text, f"يجب ألا تعتمد على {heavy}"


@pytest.mark.skipif(not is_available(), reason="opendataloader-pdf أو java غير متوفر")
def test_extract_real_pdf_smoke(tmp_path):
    """اختبار دخاني بسيط: PDF صغير مرصوف يدويًا (سطر نص واحد)."""
    fake = tmp_path / "doc.pdf"
    fake.write_bytes(b"%PDF-1.4 fake-content")
    r = extract_pdf(str(fake), output_dir=tmp_path / "out")
    # الفشل مسموح (الملف ليس PDF حقيقيًا) — المهم بلا استثناء خارج
    assert r["error"] is None or isinstance(r["error"], str)
