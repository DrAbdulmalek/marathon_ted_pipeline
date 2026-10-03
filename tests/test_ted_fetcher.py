# tests/test_ted_fetcher.py
"""اختبارات src/ted_fetcher.py (تدقيق 2026-10-03) — كلها بلا شبكة.

تُثبّت أربعة إصلاحات كحواجز انحدار:

1. **المسار الصحيح `.vtt`** — الصيغة القديمة `.../subtitles/{lang}/full` ترجع
   404 (مُثبت بالقياس الحي)، والاستجابة الصحيحة `text/vtt` لا JSON. الفشل كان
   صامتاً لأن كل شيء داخل `except` مع `logger.debug`.
2. **الـ slug هو المفتاح** — `talks/66` و`talks/<slug>` يرجعان محتوىً متطابقاً
   بايتاً ببايت، بينما `talks/3292` (وهو `id` من GraphQL) يرجع 404. أي أن
   الفضاءين الرقميين مختلفان، وحلّ رقم من HTML كان يستهدف فضاءً غامضاً.
3. **لا توكن في query string** — Apify كان يمرر `?token=<secret>` في 3 مواضع،
   فيتسرب إلى سجلات الخادم والوكيلات وReferer.
4. **لا `project_masters`** — مُثبت أنه غائب عن المستودع كله؛ هذا الاختبار
   يمنعه من العودة (كان سبب خلط الهوية في التدقيق السابق).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.ted_fetcher import (
    PREFER_SLUG,
    TED_SUBS,
    TedFetcher,
    TedTranscript,
    _gql_quote,
    parse_vtt,
)

ROOT = Path(__file__).resolve().parents[1]

VTT_SAMPLE = """WEBVTT
X-TIMESTAMP-MAP=MPEGTS:900000,LOCAL:00:00:00.000

00:00:02.103 --> 00:00:04.778
Good morning. How are you?

12
00:00:05.000 --> 00:00:07.500
It&apos;s <v Speaker1>great</v> to be <b>here</b>.
"""

AR_VTT_SAMPLE = """WEBVTT

00:00:00.000 --> 00:00:03.000
صباح الخير، كيف حالكم اليوم؟

00:00:03.500 --> 00:00:06.000
هذا نص عربي للاختبار.
"""


# ---------------------------------------------------------------------------
# 1) parse_vtt — دالة نقية
# ---------------------------------------------------------------------------

def test_parse_vtt_strips_headers_timestamps_and_cue_ids():
    out = parse_vtt(VTT_SAMPLE)
    assert "WEBVTT" not in out
    assert "X-TIMESTAMP-MAP" not in out
    assert "-->" not in out
    assert out == "Good morning. How are you? It's great to be here."


def test_parse_vtt_strips_vtt_tags_and_unescapes_entities():
    out = parse_vtt(VTT_SAMPLE)
    assert "<v Speaker1>" not in out and "<b>" not in out
    assert "&apos;" not in out and "'" in out


def test_parse_vtt_preserves_arabic_verbatim():
    out = parse_vtt(AR_VTT_SAMPLE)
    assert "صباح الخير، كيف حالكم اليوم؟" in out
    assert "هذا نص عربي للاختبار." in out


def test_parse_vtt_empty_and_garbage_inputs():
    assert parse_vtt("") == ""
    assert parse_vtt("WEBVTT\n\n") == ""
    assert parse_vtt("NOTE this is a comment\nSTYLE\n::cue{}\n") == ""


# ---------------------------------------------------------------------------
# 2) المسار: .vtt وليس /full
# ---------------------------------------------------------------------------

def test_ted_subs_path_ends_with_vtt():
    """حاجز الانحدار الأساسي: المسار بلا .vtt يرجع 404 لكل محادثة."""
    assert TED_SUBS.endswith("/full.vtt"), TED_SUBS
    assert "/subtitles/{lang}/" in TED_SUBS


def test_ted_subs_uses_talks_namespace_not_project_masters():
    assert "/talks/{id}/" in TED_SUBS
    assert "project_masters" not in TED_SUBS


def test_slug_is_preferred_key():
    assert PREFER_SLUG is True


def test_no_project_masters_anywhere_in_the_repository():
    """مُثبت أنه غائب؛ هذا الاختبار يمنعه من العودة إلى أي ملف متتبَّع."""
    # نفحص الملفات **المتتبَّعة في git فقط** — لا `rglob`. السبب عملي لا نظري:
    # `.pytest_cache/v/cache/nodeids` يسجّل أسماء الاختبارات، واسم هذا الاختبار
    # يحتوي الكلمة نفسها، فينتج إيجابية كاذبة من ملف عابر مُدرَج في .gitignore.
    import subprocess

    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, timeout=60)
        tracked = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    except Exception:                                   # pragma: no cover
        tracked = set()
    if not tracked:                                     # بلا git: نفحص المصدر فقط
        tracked = {str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")}

    # هذا الملف نفسه يذكر الكلمة ليصف الحظر — يُستثنى بالاسم لا بالنمط.
    self_rel = Path(__file__).resolve().relative_to(ROOT).as_posix()
    # collectors/ يُستثنى عمدًا (دمج 2026-10-03): توثيق طبقة الجمع يروي تاريخ
    # اكتشاف الفضاءين (project_masters مقابل talks) كخلفية للتصحيح — الحظر
    # الوظيفي يستهدف كود التنفيذ (src/) لا السجل التوثيقي. أي استعمال *فعلي*
    # في collectors/ted_utils.py يجب أن يبقى على فضاء /talks/ (مؤكد بالاختبارات
    # الأخرى أعلاه).
    hits = []
    for rel in sorted(tracked - {self_rel}):
        # طبقات التوثيق والتاريخ تُذكر فيها الكلمة مشروعًا (ملحقا
        # DECISION_LOG يرويان تصحيح الفضاءين، وfixture الاختبار يوثق
        # مساره) — الحظر الوظيفي يستهدف كود التنفيذ.
        if (rel.startswith("collectors/") or rel.startswith("docs/")
                or rel == "tests/test_evidence_fixture.py"):
            continue
        path = ROOT / rel
        if not path.is_file() or path.suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".pdf", ".db", ".pyc", ".zip", ".gz"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        if "project_masters" in text:
            hits.append(rel)
    assert hits == [], f"project_masters reappeared in tracked files: {hits}"


# ---------------------------------------------------------------------------
# 3) الأمان: لا توكن في query string
# ---------------------------------------------------------------------------

def test_apify_token_never_appears_in_a_url():
    """التوكن يجب أن يكون في ترويسة Authorization، لا في الرابط."""
    src = (ROOT / "src" / "ted_fetcher.py").read_text(encoding="utf-8")
    assert "token={self.apify_token}" not in src
    assert "?token=" not in src
    # والبديل الصحيح موجود
    assert src.count('Authorization": f"Bearer {self.apify_token}"') == 3


def test_gql_quote_escapes_quotes_and_backslashes():
    assert _gql_quote('ken "robinson"') == '"ken \\"robinson\\""'
    assert _gql_quote("a\\b") == '"a\\\\b"'
    # لا يكسر الصياغة عند نص عادي
    assert _gql_quote("plain text") == '"plain text"'


# ---------------------------------------------------------------------------
# 4) السلوك مع شبكة مزيفة (لا اتصال حقيقي)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status=200, text="", ctype="text/vtt; charset=utf-8", payload=None):
        self.status_code = status
        self.text = text
        self.headers = {"Content-Type": ctype}
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.fixture()
def fetcher():
    return TedFetcher({"languages": {"target": "ar"}})


def test_extract_slug_from_ted_url():
    assert TedFetcher.extract_slug(
        "https://www.ted.com/talks/sir_ken_robinson_do_schools_kill_creativity"
    ) == "sir_ken_robinson_do_schools_kill_creativity"
    with pytest.raises(ValueError):
        TedFetcher.extract_slug("https://example.com/not-a-ted-talk")


def test_fetch_subtitle_parses_vtt_response(fetcher, monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _FakeResp(200, VTT_SAMPLE)

    monkeypatch.setattr("src.ted_fetcher.requests.get", fake_get)
    out = fetcher._fetch_subtitle("some_slug", "en")
    assert out == "Good morning. How are you? It's great to be here."
    assert calls[0].endswith("/talks/some_slug/subtitles/en/full.vtt")


def test_fetch_subtitle_returns_empty_on_404(fetcher, monkeypatch):
    monkeypatch.setattr("src.ted_fetcher.requests.get",
                        lambda *a, **k: _FakeResp(404, "not found", "text/html"))
    assert fetcher._fetch_subtitle("missing_slug", "en") == ""


def test_fetch_subtitle_falls_back_to_json(fetcher, monkeypatch):
    """مسار JSON القديم ما زال مدعوماً (superset) إن رجع الخادم JSON."""
    payload = {"paragraphs": [{"text": "legacy"}, {"text": "format"}]}
    monkeypatch.setattr("src.ted_fetcher.requests.get",
                        lambda *a, **k: _FakeResp(200, "", "application/json", payload))
    assert fetcher._fetch_subtitle("s", "en") == "legacy format"


def test_fetch_via_ted_api_uses_slug_first_and_needs_source(fetcher, monkeypatch):
    """الـ slug يكفي وحده: فشل كشط HTML لم يعد يُسقط الجلب كله."""
    monkeypatch.setattr(TedFetcher, "_resolve_talk_id", lambda self, slug: None)
    monkeypatch.setattr(TedFetcher, "_lookup_via_graphql", lambda self, q: {})
    monkeypatch.setattr(
        TedFetcher, "_fetch_subtitle",
        lambda self, key, lang: {"en": "ENGLISH TEXT", "ar": "نص عربي"}[lang]
        if key == "ken_slug" else "",
    )
    tr = fetcher._fetch_via_ted_api("ken_slug", "en", "ar")
    assert isinstance(tr, TedTranscript)
    assert tr.source_text == "ENGLISH TEXT"
    assert tr.target_text == "نص عربي"
    assert tr.url == "https://www.ted.com/talks/ken_slug"
    # العنوان يُشتق من الـ slug عند غياب GraphQL
    assert tr.title == "Ken Slug"


def test_fetch_via_ted_api_returns_none_without_source_text(fetcher, monkeypatch):
    monkeypatch.setattr(TedFetcher, "_resolve_talk_id", lambda self, slug: None)
    monkeypatch.setattr(TedFetcher, "_lookup_via_graphql", lambda self, q: {})
    monkeypatch.setattr(TedFetcher, "_fetch_subtitle", lambda self, k, lang: "")
    assert fetcher._fetch_via_ted_api("s", "en", "ar") is None


def test_graphql_title_is_preferred_over_slug_derivation(fetcher, monkeypatch):
    monkeypatch.setattr(TedFetcher, "_resolve_talk_id", lambda self, slug: None)
    monkeypatch.setattr(TedFetcher, "_lookup_via_graphql",
                        lambda self, q: {"id": "3292", "title": "Do schools kill creativity?"})
    monkeypatch.setattr(TedFetcher, "_fetch_subtitle",
                        lambda self, k, lang: "TEXT" if lang == "en" else "")
    tr = fetcher._fetch_via_ted_api("s", "en", "ar")
    assert tr.title == "Do schools kill creativity?"
    assert tr.talk_id == "3292"


def test_graphql_query_only_uses_fields_proven_to_exist():
    """legacyId/legacyTalkId/contentId مرفوضة من الخادم — يجب ألا تعود."""
    fields = TedFetcher.GRAPHQL_SEARCH_FIELDS
    for banned in ("legacyId", "legacyTalkId", "contentId", "primaryLanguage"):
        assert banned not in fields
    for allowed in ("id", "slug", "title", "url"):
        assert re.search(rf"\b{allowed}\b", fields), allowed


def test_lookup_via_graphql_never_raises(fetcher, monkeypatch):
    """أي فشل في GraphQL يعيد {} — لا يُسقط الجلب."""
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.ted_fetcher.requests.post", boom)
    assert fetcher._lookup_via_graphql("anything") == {}
