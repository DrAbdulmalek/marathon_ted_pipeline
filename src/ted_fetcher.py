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

#: المسار الحيّ **المُثبت بالقياس** (تدقيق 2026-10-03):
#:   GET hls.ted.com/talks/sir_ken_robinson_do_schools_kill_creativity/subtitles/en/full.vtt
#:     -> 200, Content-Type: text/vtt; charset=utf-8, 30867 B, يبدأ بـ "WEBVTT"
#:   GET .../subtitles/en/full      (بلا .vtt)
#:     -> 404
#: الصيغة القديمة في هذا الملف كانت بلا `.vtt`، فكان كل جلب رسمي يفشل 404 ثم
#: يُبتلع في `except` ويُسجَّل debug فقط — فشل صامت كامل للمسار «الرسمي».
TED_SUBS = "https://hls.ted.com/talks/{id}/subtitles/{lang}/full.vtt"

#: المُعرِّف في المسار أعلاه يقبل **الـ slug** وهو المفتاح الموثوق الوحيد.
#: مُثبت: talks/66 (legacy id) و talks/<slug> يرجعان محتوىً متطابقاً بايتاً ببايت
#: (sha256 366a2faa137471155760f0bf…, 30867 B)، بينما talks/3292 — وهو `id`
#: الذي يعيده GraphQL — يرجع **404**. أي أن هناك فضاءين رقميين مختلفين، ولا
#: يمكن الاعتماد على أي رقم؛ الـ slug هو المرجع.
PREFER_SLUG = True

_UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MarathonTEDPipeline/1.0",
}


def parse_vtt(raw: str) -> str:
    """يحوّل WebVTT إلى نص متصل — دالة نقية قابلة للاختبار بلا شبكة.

    يتجاهل: سطر `WEBVTT`، `X-TIMESTAMP-MAP`، أي سترينغ بداية (NOTE/STYLE/REGION)،
    ومؤشرات الزمن `00:00:02.103 --> 00:00:04.778`، ومعرّفات الـ cue الرقمية.
    يفكّ وسوم VTT (<c>, <v Speaker>, <b>) ويحوّل الكيانات HTML الأساسية.
    """
    import html
    import re as _re

    #: كتل WebVTT التي تُتخطى **بمحتواها** حتى أول سطر فارغ (حسب المواصفة):
    #: NOTE (تعليق)، STYLE (CSS مثل ::cue{})، REGION (تعريف منطقة).
    #: تخطّي السطر الأول وحده كان يترك CSS يتسرب إلى النص.
    _BLOCK_HEADERS = ("NOTE", "STYLE", "REGION")

    lines_out: list = []
    skipping_block = False
    for line in raw.splitlines():
        s = line.strip()

        if not s:                            # سطر فارغ = نهاية أي كتلة
            skipping_block = False
            continue
        if skipping_block:
            continue
        if s.startswith(_BLOCK_HEADERS):
            skipping_block = True
            continue

        if s.startswith(("WEBVTT", "X-TIMESTAMP-MAP", "Kind:", "Language:")):
            continue
        if "-->" in s:                       # سطر توقيت
            continue
        if _re.fullmatch(r"\d{1,5}", s):     # معرّف cue رقمي
            continue
        s = _re.sub(r"<[^>]+>", "", s)        # وسوم VTT
        s = html.unescape(s)
        if s:
            lines_out.append(s)
    return " ".join(lines_out).strip()


def _gql_quote(value: str) -> str:
    """يهرّب نصاً ليصبح literal داخل استعلام GraphQL (أمان + صحة صياغة)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

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
    def _fetch_subtitle(self, key: str, lang: str) -> str:
        """يجلب ترجمة لغة واحدة لمفتاح (slug أو رقم) ويعيد نصاً أو "".

        يستدعي المسار المُثبت `.vtt` ويحلّله بـ :func:`parse_vtt`. يحتفظ بمسار
        JSON احتياطي لأن TED غيّر صيغ التوزيع سابقاً؛ أي استجابة غير VTT
        تُجرَّب كـ JSON بدل أن تُرمى بصمت.
        """
        url = TED_SUBS.format(id=key, lang=lang)
        r = requests.get(url, headers=_UA, timeout=self.timeout)
        if r.status_code != 200:
            logger.debug("ترجمة %s/%s -> HTTP %s", key, lang, r.status_code)
            return ""
        ctype = (r.headers.get("Content-Type") or "").lower()
        body = r.text
        if "vtt" in ctype or body.lstrip().startswith("WEBVTT"):
            return parse_vtt(body)
        try:                                 # مسار قديم/احتياطي: JSON
            data = r.json()
        except ValueError:
            logger.warning("استجابة غير VTT وغير JSON من %s", url)
            return ""
        paragraphs = data.get("paragraphs") or data.get("captions") or []
        return " ".join(p.get("text", "") for p in paragraphs).strip()

    def _fetch_via_ted_api(
        self, slug: str, source_lang: str, target_lang: str
    ) -> Optional[TedTranscript]:
        """الـ slug أولاً — لا حاجة لحلّ رقمي ولا لكشط HTML.

        مُثبت بالقياس (2026-10-03): الـ slug يعمل مباشرة على hls.ted.com، بينما
        الأرقام تنتمي لفضاءين مختلفين (legacy يعمل، و`id` من GraphQL يرجع 404).
        لذلك `_resolve_talk_id` صار **سنداً احتياطياً** لا شرطاً؛ وكان سابقاً
        شرطاً يُسقط الجلب كله عند فشل كشط HTML.
        """
        candidates = [slug] if PREFER_SLUG else []
        talk_id = self._resolve_talk_id(slug)
        if talk_id:
            candidates.append(str(talk_id))
        if not candidates:
            logger.debug("لا slug ولا talk_id للجلب الرسمي")
            return None

        result: dict = {}
        used_key = None
        for key in candidates:
            for lang in (source_lang, target_lang):
                if not lang or lang in result:
                    continue
                try:
                    text = self._fetch_subtitle(key, lang)
                except Exception as exc:
                    logger.debug("فشل جلب ترجمة %s (%s): %s", lang, key, exc)
                    continue
                if text:
                    result[lang] = text
                    used_key = key
        if source_lang not in result and "en" not in result:
            return None

        meta = self._lookup_via_graphql(slug)
        title = meta.get("title") or slug.replace("_", " ").title()
        return TedTranscript(
            talk_id=str(meta.get("id") or used_key or slug),
            title=title.strip(),
            url=f"https://www.ted.com/talks/{slug}",
            source_text=result.get(source_lang, ""),
            target_text=result.get(target_lang),
            source_lang=source_lang,
        )

    # ---------- GraphQL: بيانات وصفية (مُثبت أنه يعمل بلا مفتاح) ----------
    #: الحقول المُثبت قبولها (2026-10-03). الحقول legacyId/legacyTalkId/
    #: contentId/language/primaryLanguage **مرفوضة** من الخادم
    #: (GRAPHQL_VALIDATION_FAILED: Cannot query field)، وintrospection معطّل
    #: (INTROSPECTION_DISABLED) — لذلك تُختبر الحقول تجريبياً لا بالحدس.
    GRAPHQL_SEARCH_FIELDS = "id slug title url description publishedAt"

    def _lookup_via_graphql(self, query: str) -> dict:
        """يعيد بيانات أول نتيجة بحث، أو {} عند أي فشل (لا يُفشل الجلب أبداً)."""
        try:
            r = requests.post(
                TED_API,
                json={"query": "{search(q:%s){results{... on SearchTalk{%s}}}}"
                             % (_gql_quote(query), self.GRAPHQL_SEARCH_FIELDS)},
                headers={**_UA, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return {}
            results = (((r.json() or {}).get("data") or {}).get("search") or {}).get("results") or []
            for item in results:
                if isinstance(item, dict) and item.get("slug"):
                    return item
        except Exception as exc:
            logger.debug("GraphQL غير متاح: %s", exc)
        return {}

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
            # أمان: التوكن في الترويسة لا في الـ query string. وجوده في الرابط
            # يعني تسرّبه إلى سجلات الخادم والوكيلات وترويسة Referer — وهو
            # تسريب اعتماد دائم لا يُصلحه تدوير المفتاح وحده.
            run = requests.post(
                "https://api.apify.com/v2/acts/dtrungjin~ted-talk-scraper/runs",
                json={"startUrls": [{"url": ted_url}]},
                headers={"Authorization": f"Bearer {self.apify_token}"},
                timeout=self.timeout,
            )
            run.raise_for_status()
            run_id = run.json()["data"]["id"]
            for _ in range(30):  # حتى ~90 ثانية
                time.sleep(3)
                st = requests.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers={"Authorization": f"Bearer {self.apify_token}"},
                    timeout=self.timeout,
                ).json()
                if st["data"]["status"] in ("SUCCEEDED", "FAILED"):
                    break
            if st["data"]["status"] != "SUCCEEDED":
                return None
            items = requests.get(
                f"https://api.apify.com/v2/datasets/"
                f"{st['data']['defaultDatasetId']}/items",
                headers={"Authorization": f"Bearer {self.apify_token}"},
                timeout=self.timeout,
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
