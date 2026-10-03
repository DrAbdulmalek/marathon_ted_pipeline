# src/ted_fetcher.py
"""
جالب محادثات TED — ثلاثة أنماط بالترتيب:
1. TED.com API الرسمي (subtitles endpoint)
2. خدمة ted2srt_py المحلية (TED2SRT_ENDPOINT)
3. Apify scraper (APIFY_TOKEN) — آخر سند
"""
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TED_API = "https://www.ted.com/graphql"
TED_SUBS = "https://hls.ted.com/talks/{id}/subtitles/{lang}/full"
_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MarathonTEDPipeline/1.0",
}


@dataclass
class TedTranscript:
    talk_id: str
    title: str
    url: str
    source_text: str
    target_text: Optional[str]
    source_lang: str = "en"


class TedFetcher:
    """جلب نص محادثة TED وترجمتها الرسمية إن وُجدت."""

    def __init__(self, config: dict):
        self.config = config
        self.ted2srt_endpoint = os.getenv(
            "TED2SRT_ENDPOINT", "http://ted2srt_py:3002"
        )
        self.apify_token = os.getenv("APIFY_TOKEN", "")
        self.timeout = 45

    # ---------- أدوات ----------
    @staticmethod
    def extract_slug(ted_url: str) -> str:
        """استخراج الـ slug من رابط TED."""
        m = re.search(r"/talks/([a-z0-9_]+)", ted_url, re.I)
        if not m:
            raise ValueError(f"رابط TED غير صالح: {ted_url}")
        return m.group(1)

    def _resolve_talk_id(self, slug: str) -> Optional[int]:
        """النمط 1أ: حل رقم المحادثة من صفحة الـ talk."""
        try:
            r = requests.get(
                f"https://www.ted.com/talks/{slug}",
                headers=_UA, timeout=self.timeout,
            )
            m = re.search(r"talks/(\d+)(?:\.json)?", r.text)
            m2 = re.search(r'"id":\s*(\d{4,6})', r.text)
            return int((m or m2).group(1)) if (m or m2) else None
        except Exception as exc:
            logger.debug("تعذر حل talk_id: %s", exc)
            return None

    # ---------- النمط 1: TED الرسمي ----------
    def _fetch_via_ted_api(
        self, slug: str, source_lang: str, target_lang: str
    ) -> Optional[TedTranscript]:
        talk_id = self._resolve_talk_id(slug)
        if not talk_id:
            return None
        result = {}
        for lang in (source_lang, target_lang):
            if not lang:
                continue
            try:
                r = requests.get(
                    TED_SUBS.format(id=talk_id, lang=lang),
                    headers=_UA, timeout=self.timeout,
                )
                if r.status_code != 200:
                    continue
                data = r.json()
                paragraphs = (
                    data.get("paragraphs", [])
                    or data.get("captions", [])
                )
                text = " ".join(
                    p.get("text", "") for p in paragraphs
                ).strip()
                if text:
                    result[lang] = text
            except Exception as exc:
                logger.debug("فشل جلب ترجمة %s: %s", lang, exc)
        if "en" not in result and source_lang not in result:
            return None
        return TedTranscript(
            talk_id=str(talk_id),
            title=slug.replace("_", " ").title(),
            url=f"https://www.ted.com/talks/{slug}",
            source_text=result.get(source_lang, ""),
            target_text=result.get(target_lang),
            source_lang=source_lang,
        )

    # ---------- النمط 2: خدمة ted2srt_py المحلية ----------
    def _fetch_via_ted2srt(
        self, ted_url: str, target_lang: str
    ) -> Optional[TedTranscript]:
        try:
            r = requests.post(
                f"{self.ted2srt_endpoint}/fetch",
                json={"url": ted_url, "lang": target_lang},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data.get("source_text"):
                return None
            return TedTranscript(
                talk_id=str(data.get("talk_id", "")),
                title=data.get("title", ""),
                url=ted_url,
                source_text=data["source_text"],
                target_text=data.get("target_text"),
                source_lang=data.get("source_lang", "en"),
            )
        except Exception as exc:
            logger.debug("ted2srt_py غير متاح: %s", exc)
            return None

    # ---------- النمط 3: Apify ----------
    def _fetch_via_apify(
        self, ted_url: str, target_lang: str
    ) -> Optional[TedTranscript]:
        if not self.apify_token:
            return None
        try:
            run = requests.post(
                f"https://api.apify.com/v2/acts/dtrungjin~ted-talk-scraper"
                f"/runs?token={self.apify_token}",
                json={"startUrls": [{"url": ted_url}]},
                timeout=self.timeout,
            )
            run.raise_for_status()
            run_id = run.json()["data"]["id"]
            for _ in range(30):  # حتى ~90 ثانية
                time.sleep(3)
                st = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}"
                    f"?token={self.apify_token}", timeout=self.timeout,
                ).json()
                if st["data"]["status"] in ("SUCCEEDED", "FAILED"):
                    break
            if st["data"]["status"] != "SUCCEEDED":
                return None
            items = requests.get(
                f"https://api.apify.com/v2/datasets/"
                f"{st['data']['defaultDatasetId']}/items"
                f"?token={self.apify_token}", timeout=self.timeout,
            ).json()
            if not items:
                return None
            it = items[0]
            return TedTranscript(
                talk_id=str(it.get("talkId", "")),
                title=it.get("title", ""),
                url=ted_url,
                source_text=it.get("transcript", ""),
                target_text=it.get("translation"),
                source_lang="en",
            )
        except Exception as exc:
            logger.debug("Apify فشل: %s", exc)
            return None

    # ---------- الواجهة العامة ----------
    def fetch(
        self, ted_url: str, target_lang: str = None,
        source_lang: str = "en",
    ) -> Optional[TedTranscript]:
        """جلب الترجمة للغة محددة — يجرب الأنماط الثلاثة بالترتيب.

        source_lang قابل للضبط: مرّر "ar" لجلب النسخة العربية كمصدر —
        النمط الرسمي يدعم أي لغة متاحة على TED عبر hls.ted.com.
        (ted2srt/Apify يبقيان المصدر الأصلي للمحادثة كما هي خدماتهما.)
        """
        target_lang = target_lang or self.config.get(
            "languages", {}
        ).get("target", "ar")
        slug = self.extract_slug(ted_url)

        logger.info("جلب المحادثة: %s (مصدر: %s هدف: %s)",
                    slug, source_lang, target_lang)
        for fetcher, name in (
            (lambda: self._fetch_via_ted_api(
                slug, source_lang, target_lang), "ted-api"),
            (lambda: self._fetch_via_ted2srt(ted_url, target_lang), "ted2srt"),
            (lambda: self._fetch_via_apify(ted_url, target_lang), "apify"),
        ):
            try:
                transcript = fetcher()
            except Exception as exc:
                logger.warning("خطأ في نمط %s: %s", name, exc)
                transcript = None
            if transcript and transcript.source_text:
                logger.info("نجح النمط: %s", name)
                return transcript
        logger.error("فشلت الأنماط الثلاثة لجلب: %s", ted_url)
        return None
