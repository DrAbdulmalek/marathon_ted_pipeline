# tests/test_evidence_fixture.py
"""قفل fixture الدليل الحي — أول بايتات فعلية جُلبت من TED في تاريخ المشروع.

المصدر: https://hls.ted.com/project_masters/8593/subtitles/ar/full.vtt
مُثبت حيًا: HTTP 200، 16,710B، 0.46s (2026-10-03).
هذا الملف هو المرجع الثابت لكل اختبارات E2E المستقبلية — لا تُعدّله يدويًا.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/evidence/talk_8593_ar.vtt"


@pytest.fixture(scope="module")
def vtt_bytes() -> bytes:
    assert FIXTURE.exists(), f"fixture الدليل غائب: {FIXTURE}"
    return FIXTURE.read_bytes()


def test_evidence_fixture_size(vtt_bytes):
    """16,710 بايت وقت الالتقاط — يمنع استبدال صامت بملف فارغ/مقطوع."""
    assert len(vtt_bytes) >= 16_000, f"حجم غير متوقع: {len(vtt_bytes)}B"


def test_evidence_fixture_is_real_vtt(vtt_bytes):
    """هيدر WEBVTT وطوابع زمنية — بنية VTT حقيقية لا نص محفوظ أعماً."""
    text = vtt_bytes.decode("utf-8")
    assert text.lstrip("\ufeff").startswith("WEBVTT")
    assert "-->" in text, "لا طوابع زمنية — ليس VTT صالحًا"


def test_evidence_fixture_is_arabic_content(vtt_bytes):
    """محتوى عربي فعلي (نطاق Unicode العربي) — ما جلبناه فعلًا من TED."""
    text = vtt_bytes.decode("utf-8")
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    assert arabic > 500, f"محتوى عربي ضعيف: {arabic} حرفًا فقط"
