"""Local TED subtitle adapter.

Endpoints:
- POST /fetch {"url": "...", "lang": "ar"} -> English + requested-language text.
- POST /srt {"url": "...", "lang": "ar"} -> timed SRT for requested language.
- GET /health -> health check.

Uses TED's VTT subtitle endpoint directly. No numeric talk-ID scraping and no
third-party API token are required. A missing translation is reported as such;
it is never replaced with English and labelled Arabic.
"""
from __future__ import annotations

import html
import logging
import re
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MarathonTEDPipeline/1.1",
}
TED_VTT = "https://hls.ted.com/talks/{slug}/subtitles/{lang}/full.vtt"
TIME_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})(?:\s+.*)?$"
)
TAG_RE = re.compile(r"<[^>]*>")


def _talk_slug(url: str) -> str:
    """Validate TED URL and return its talk slug."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"ted.com", "www.ted.com"}:
        raise ValueError("url must be an https://www.ted.com/talks/... URL")
    match = re.fullmatch(r"/talks/([A-Za-z0-9_-]+)(?:\.html)?/?", parsed.path)
    if not match:
        raise ValueError("URL does not contain a valid TED talk slug")
    return match.group(1)


def _language_code(value: str) -> str:
    value = (value or "ar").strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", value):
        raise ValueError("invalid language code")
    return value


def _fetch_vtt(slug: str, lang: str) -> str | None:
    response = requests.get(
        TED_VTT.format(slug=slug, lang=lang),
        headers=_UA,
        timeout=45,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    body = response.text.lstrip("\ufeff")
    if not body.startswith("WEBVTT"):
        raise ValueError(f"TED returned a non-WebVTT response for language {lang}")
    return body


def _vtt_cues(raw: str) -> list[tuple[str, str, str]]:
    """Parse timed VTT cues while preserving cue order and timing."""
    cues: list[tuple[str, str, str]] = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = TIME_RE.match(line)
        if not match:
            i += 1
            continue
        start, end = match.group("start", "end")
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            candidate = lines[i].strip()
            if TIME_RE.match(candidate):
                break
            candidate = html.unescape(TAG_RE.sub("", candidate)).strip()
            if candidate:
                text_lines.append(candidate)
            i += 1
        text = " ".join(text_lines).strip()
        if text:
            cues.append((start, end, text))
    return cues


def _to_srt_timestamp(value: str) -> str:
    return value.replace(".", ",")


def _to_srt(raw: str) -> str:
    blocks = []
    for index, (start, end, text) in enumerate(_vtt_cues(raw), start=1):
        blocks.append(
            f"{index}\n{_to_srt_timestamp(start)} --> "
            f"{_to_srt_timestamp(end)}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _plain_text(raw: str) -> str:
    return " ".join(cue[2] for cue in _vtt_cues(raw)).strip()


@app.get("/health")
def health():
    return jsonify(status="ok", service="ted2srt_py")


@app.post("/fetch")
def fetch():
    body = request.get_json(silent=True) or {}
    try:
        slug = _talk_slug(str(body.get("url", "")))
        target_lang = _language_code(str(body.get("lang", "ar")))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    try:
        source_vtt = _fetch_vtt(slug, "en")
        if not source_vtt:
            return jsonify(error="No English subtitles available", slug=slug), 404
        target_vtt = _fetch_vtt(slug, target_lang)
    except requests.RequestException:
        logger.exception("TED subtitle request failed for %s", slug)
        return jsonify(error="TED subtitle service unavailable"), 502
    except ValueError as exc:
        logger.warning("Invalid TED subtitle response for %s: %s", slug, exc)
        return jsonify(error="TED returned an invalid subtitle response"), 502

    if not target_vtt:
        return jsonify(
            error=f"No subtitles available for language '{target_lang}'",
            slug=slug,
            source_lang="en",
            target_lang=target_lang,
            source_text=_plain_text(source_vtt),
            target_text=None,
        ), 404

    return jsonify(
        talk_id=slug,
        title=slug.replace("_", " ").replace("-", " ").title(),
        url=f"https://www.ted.com/talks/{slug}",
        source_lang="en",
        target_lang=target_lang,
        source_text=_plain_text(source_vtt),
        target_text=_plain_text(target_vtt),
    )


@app.post("/srt")
def srt():
    body = request.get_json(silent=True) or {}
    try:
        slug = _talk_slug(str(body.get("url", "")))
        lang = _language_code(str(body.get("lang", "ar")))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    try:
        raw = _fetch_vtt(slug, lang)
    except requests.RequestException:
        logger.exception("TED subtitle request failed for %s/%s", slug, lang)
        return jsonify(error="TED subtitle service unavailable"), 502
    except ValueError:
        return jsonify(error="TED returned an invalid subtitle response"), 502

    if not raw:
        return jsonify(error=f"No subtitles available for language '{lang}'"), 404
    return jsonify(
        talk_id=slug,
        language=lang,
        srt=_to_srt(raw),
    )


if __name__ == "__main__":
    import os

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3002")))
