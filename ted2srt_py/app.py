# ted2srt_py/app.py
"""
خدمة ted2srt_py — بديل محلي لخدمة ted2srt (Flask):
- /fetch  POST {url, lang} → نص المحادثة + الترجمة
- /srt    POST {url, lang} → ملف SRT
- /health GET
تعمل على PORT=3002 داخل شبكة compose.
"""
import logging
import os
import re

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ted2srt_py/1.0",
}
PORT = int(os.getenv("PORT", "3002"))


def _talk_id_from_page(url: str):
    r = requests.get(url, headers=_UA, timeout=45)
    m = re.search(r"talks/(\d+)(?:\.json)?", r.text)
    m2 = re.search(r'"id":\s*(\d{4,6})', r.text)
    return int((m or m2).group(1)) if (m or m2) else None


def _subtitles(talk_id: int, lang: str):
    r = requests.get(
        f"https://hls.ted.com/talks/{talk_id}/subtitles/{lang}/full",
        headers=_UA, timeout=45,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    paragraphs = data.get("paragraphs") or data.get("captions") or []
    return " ".join(p.get("text", "") for p in paragraphs).strip()


@app.get("/health")
def health():
    return jsonify(status="ok", service="ted2srt_py")


@app.post("/fetch")
def fetch():
    """جلب نص محادثة TED + ترجمتها الرسمية إن وُجدت."""
    body = request.get_json(force=True)
    url = body.get("url", "")
    lang = body.get("lang", "ar")
    if "/talks/" not in url:
        return jsonify(error="رابط TED غير صالح"), 400

    slug = re.search(r"/talks/([a-z0-9_]+)", url, re.I).group(1)
    talk_id = _talk_id_from_page(url)
    if not talk_id:
        return jsonify(error="تعذر حل رقم المحادثة"), 502

    source = _subtitles(talk_id, "en") or ""
    target = _subtitles(talk_id, lang)
    if not source:
        return jsonify(error="لا توجد ترجمة إنجليزية"), 404

    return jsonify(
        talk_id=talk_id,
        title=slug.replace("_", " ").title(),
        source_lang="en",
        source_text=source,
        target_text=target,
    )


@app.post("/srt")
def srt():
    """توليد ملف SRT من محادثة TED."""
    body = request.get_json(force=True)
    url = body.get("url", "")
    lang = body.get("lang", "ar")
    talk_id = _talk_id_from_page(url)
    if not talk_id:
        return jsonify(error="تعذر حل رقم المحادثة"), 502

    r = requests.get(
        f"https://hls.ted.com/talks/{talk_id}/subtitles/{lang}/full",
        headers=_UA, timeout=45,
    )
    if r.status_code != 200:
        return jsonify(error="لا توجد ترجمة بهذه اللغة"), 404

    data = r.json()
    cues = data.get("captions") or data.get("paragraphs") or []

    def _ts(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3600000)
        m_, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m_:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, cue in enumerate(cues, 1):
        start = cue.get("startTime", cue.get("start", 0))
        dur = cue.get("duration", 3000)
        text = cue.get("text", "")
        lines.append(str(i))
        lines.append(f"{_ts(start/1000.0)} --> {_ts((start+dur)/1000.0)}")
        lines.append(text)
        lines.append("")
    srt_text = "\n".join(lines)
    return jsonify(talk_id=talk_id, srt=srt_text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
