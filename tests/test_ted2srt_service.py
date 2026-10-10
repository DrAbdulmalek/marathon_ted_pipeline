from __future__ import annotations

from unittest.mock import Mock

import pytest

from ted2srt_py import app as service


VTT = """WEBVTT

00:00:00.000 --> 00:00:02.500
<v Speaker1>Hello <b>world</b>!</v>

00:00:02.500 --> 00:00:04.000
It&apos;s nice to meet you.
"""


def test_talk_slug_rejects_non_ted_hosts():
    with pytest.raises(ValueError):
        service._talk_slug("https://ted.com.attacker.example/talks/demo")


def test_talk_slug_accepts_standard_ted_url():
    assert service._talk_slug("https://www.ted.com/talks/a_talk?language=ar") == "a_talk"


def test_vtt_to_srt_preserves_timing_and_decodes_markup():
    result = service._to_srt(VTT)
    assert "1\n00:00:00,000 --> 00:00:02,500\nHello world!" in result
    assert "2\n00:00:02,500 --> 00:00:04,000\nIt's nice to meet you." in result


def test_fetch_returns_bilingual_text_and_uses_slug_endpoint(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        response = Mock(status_code=200, text=VTT)
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(service.requests, "get", fake_get)
    client = service.app.test_client()
    response = client.post(
        "/fetch",
        json={"url": "https://www.ted.com/talks/a_talk", "lang": "ar"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["source_text"] == "Hello world! It's nice to meet you."
    assert data["target_text"] == data["source_text"]
    assert calls == [
        "https://hls.ted.com/talks/a_talk/subtitles/en/full.vtt",
        "https://hls.ted.com/talks/a_talk/subtitles/ar/full.vtt",
    ]


def test_missing_target_language_is_not_mislabeled_as_translation(monkeypatch):
    def fake_get(url, **kwargs):
        if "/subtitles/ar/" in url:
            return Mock(status_code=404, text="")
        response = Mock(status_code=200, text=VTT)
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(service.requests, "get", fake_get)
    response = service.app.test_client().post(
        "/fetch",
        json={"url": "https://www.ted.com/talks/a_talk", "lang": "ar"},
    )
    assert response.status_code == 404
    data = response.get_json()
    assert data["source_text"]
    assert data["target_text"] is None
