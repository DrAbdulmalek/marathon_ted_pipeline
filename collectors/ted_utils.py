#!/usr/bin/env python3
"""دوال مشتركة لماراثون TED."""
import json
import re
import time
import requests
from pathlib import Path

BASE = Path(__file__).parent.parent
DATA = BASE / "data"
DOWNLOADS = DATA / "downloads"
READY = DATA / "ready"
LOGS = BASE / "logs"

for d in (DATA, DOWNLOADS, READY, LOGS):
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

# لغات مدعومة على hls.ted.com
LANG_CODES = {
    "en": "en", "ar": "ar", "fr": "fr", "es": "es", "de": "de",
    "tr": "tr", "fa": "fa", "ur": "ur", "zh-cn": "zh-cn", "ru": "ru",
    "pt": "pt", "it": "it", "ja": "ja", "ko": "ko", "he": "he",
    "hi": "hi", "nl": "nl", "pl": "pl",
}


def extract_talk_id(talk_url: str, session: requests.Session = None) -> str | None:
    """استخرج talk_id من صفحة المحادثة — الطريقة المؤكدة من [7]."""
    sess = session or requests
    try:
        r = sess.get(talk_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        # الطريقة المستخدمة في remzicam/ted_talks_summarizer [7†L21-L23]
        if "project_masters/" in r.text:
            tid = r.text.split("project_masters/")[1].split("/")[0]
            if tid.isdigit():
                return tid
        # احتياطي: ابحث عن talkId في JSON
        m = re.search(r'"talkId"\s*:\s*(\d+)', r.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def download_vtt(talk_id: str, lang: str = "en",
                  session: requests.Session = None) -> str | None:
    """
    حمّل VTT من hls.ted.com مباشرة.

    ⚠️ تصحيح حاسم 2026-10-03 (مسح كامل + مطابقة محتوى):
    المساحة الصحيحة هي /talks/{id}/ لا /project_masters/{id}/.
    الدليل: 8/8 أزواج willard مطابقة لمحتوى slug عبر /talks/ (daphne 85 إصابة)
    و 1136 = Phyllis Rodriguez (9_11_healing) عبر /talks/ بينما /project_masters/1136
    محادثة أخرى تمامًا (صفر كلمات 9/11). النسختان مختلفتان بايتيًا (md5 مختلف).
    الخريطة الحية المُتحقَّقة: 1,640/1,669 willard عبر /talks/ (98%).
    الرابط المؤكد: https://hls.ted.com/talks/{talk_id}/subtitles/{lang}/full.vtt
    """
    sess = session or requests
    url = (
        f"https://hls.ted.com/talks/"
        f"{talk_id}/subtitles/{lang}/full.vtt"
    )
    try:
        r = sess.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and len(r.text) > 50:
            return r.text
    except Exception:
        pass
    return None


def vtt_to_srt(vtt_text: str) -> str:
    """تحويل VTT إلى SRT."""
    lines = vtt_text.replace("\r\n", "\n").split("\n")
    out = []
    idx = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            ts = line.replace(".", ",")
            # أزل أي metadata إضافية بعد timestamp
            ts = ts.split("align:")[0].strip()
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            if text_lines:
                out.append(str(idx))
                out.append(ts)
                out.extend(text_lines)
                out.append("")
                idx += 1
        i += 1
    return "\n".join(out)


def vtt_to_plain_text(vtt_text: str) -> str:
    """استخرج النص العادي من VTT (بلا timestamps)."""
    lines = vtt_text.replace("\r\n", "\n").split("\n")
    text_parts = []
    skip_next = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") \
           or line.startswith("Language:"):
            continue
        if "-->" in line:
            skip_next = False
            continue
        # إزالة الترقيم داخل الأقواس المربعة
        clean = re.sub(r"\[.*?\]", "", line).strip()
        if clean:
            text_parts.append(clean)
    # دمج الجمل المتقاربة
    text = " ".join(text_parts)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([،,.!?؟])", r"\1", text)
    return text.strip()


def srt_to_markdown(srt_text: str, title: str, url: str,
                    lang: str = "ar") -> str:
    """تحويل SRT إلى Markdown منسّق للرفع."""
    dir_attr = ' dir="rtl"' if lang == "ar" else ""
    md = [f"# {title}\n"]
    md.append(f"**الرابط:** {url}\n")
    md.append(f"**اللغة:** {lang.upper()}\n")
    md.append("---\n")

    # استخراج المقاطع
    blocks = srt_text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        timecode = lines[1] if "-->" in lines[1] else ""
        text = " ".join(lines[2:]).strip()
        if text:
            start = timecode.split("-->")[0].strip() if timecode else ""
            if start:
                md.append(f"**[{start}]** {text}\n")
            else:
                md.append(f"{text}\n")
    return "\n".join(md)


def slug_from_url(url: str) -> str:
    """استخرج slug من رابط TED."""
    return url.rstrip("/").split("/talks/")[-1].split("?")[0]


def safe_filename(s: str, max_len: int = 80) -> str:
    """تنظيف اسم ملف."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len] or "untitled"


def load_json(path: Path) -> list | dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
