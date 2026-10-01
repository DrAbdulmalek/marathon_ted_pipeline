# src/translator.py
"""
محركات الترجمة:
- GoogleTranslator  (deep-translator)
- DeepLTranslator   (deepl REST)
- HFTranslator      (Helsinki-NLP / NLLB عبر transformers — تحميل كسول)
- FinetunedTranslator (نماذج مُدرَّبة محليًا على TED — finetune/)
- MultiLangTranslator (10 لغات RTL/LTR عبر registry)
الواجهة الموحدة: translate(text, src, tgt) -> TranslationResult
"""
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    translated_text: str
    engine: str = "google"
    src: str = "auto"
    tgt: str = "ar"
    meta: dict = None

    def __post_init__(self):
        if self.meta is None:
            self.meta = {}


class BaseTranslator:
    """الواجهة المجردة لكل المحركات."""

    engine = "base"

    def translate(self, text: str, src: str = "auto", tgt: str = "ar") -> TranslationResult:
        raise NotImplementedError


class GoogleTranslator(BaseTranslator):
    """المحرك الأول — deep-translator (مجاني، بلا مفتاح)."""

    def __init__(self, **kwargs):
        self.engine = "google"

    def translate(self, text: str, src: str = "auto", tgt: str = "ar") -> TranslationResult:
        if not text.strip():
            return TranslationResult("", self.engine, src, tgt)
        from deep_translator import GoogleTranslator as _DTGoogle

        source = src if src and src != "auto" else "auto"
        translator = _DTGoogle(source=source, target=tgt)
        # deep-translator يعلق على النصوص الطويلة — تقسيم عند الحاجة
        chunks = self._chunk(text)
        out = " ".join(translator.translate(c) for c in chunks if c.strip())
        return TranslationResult(out, self.engine, src, tgt)

    @staticmethod
    def _chunk(text: str, size: int = 4500) -> list:
        if len(text) <= size:
            return [text]
        parts, buf = [], ""
        for sent in re.split(r"(?<=[.!؟?])\s+", text):
            if len(buf) + len(sent) + 1 > size:
                if buf:
                    parts.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf:
            parts.append(buf)
        return parts


class DeepLTranslator(BaseTranslator):
    """المحرك الثاني — DeepL API (يتطلب DEEPL_API_KEY)."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.engine = "deepl"
        self.api_key = api_key or os.getenv("DEEPL_API_KEY", "")
        if not self.api_key:
            logger.warning("DEEPL_API_KEY غير مضبوط — سي فشل الاستدعاء")

    def translate(self, text: str, src: str = "auto", tgt: str = "ar") -> TranslationResult:
        if not text.strip():
            return TranslationResult("", self.engine, src, tgt)
        import requests

        source = None if (not src or src == "auto") else src.upper()
        resp = requests.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            data={
                "text": text,
                "target_lang": (tgt or "ar").upper(),
                **({"source_lang": source} if source else {}),
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        out = data["translations"][0]["text"]
        return TranslationResult(out, self.engine, src, tgt)


class HFTranslator(BaseTranslator):
    """المحرك الثالث — نماذج MarianMT/NLLB محليًا (تحميل كسول)."""

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        self.engine = "hf"
        self.model_name = model_name or "Helsinki-NLP/opus-mt-en-ar"
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            from transformers import pipeline

            logger.info("تحميل نموذج HF: %s", self.model_name)
            self._pipeline = pipeline(
                "translation", model=self.model_name, device=-1
            )
        return self._pipeline

    def translate(self, text: str, src: str = "auto", tgt: str = "ar") -> TranslationResult:
        if not text.strip():
            return TranslationResult("", self.engine, src, tgt)
        pipe = self._load()
        # تقسيم لقطات قصيرة (حد النماذج 512 توكن)
        chunks = [c for c in re.split(r"(?<=[.!؟?])\s+", text) if c.strip()]
        outs = []
        for chunk in chunks:
            res = pipe(chunk, max_length=512, truncation=True)
            outs.append(res[0]["translation_text"])
        return TranslationResult(" ".join(outs), self.engine, src, tgt)


# إضافة محرك رابع: fine-tuned
class FinetunedTranslator(BaseTranslator):
    def __init__(self, model_dir: str = "finetune/models/ted_ar_v1"):
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_dir).to(self.device)
        self.model.eval()
        self.engine = "finetuned-ted"

    def translate(self, text: str, src: str = "en", tgt: str = "ar") -> str:
        import torch
        if not text.strip():
            return ""
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256,
        ).to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_length=256)
        return self.tokenizer.decode(out[0], skip_special_tokens=True)


_ENGINES = {
    "google": GoogleTranslator,
    "deepl": DeepLTranslator,
    "hf": HFTranslator,
    "finetuned": FinetunedTranslator,
}


class Translator:
    """واجهة موحدة تختار المحرك بالاسم."""

    def __init__(self, engine: str = "google", **kwargs):
        if engine not in _ENGINES:
            raise ValueError(
                f"محرك غير معروف: {engine}. المتاح: {list(_ENGINES)}"
            )
        self.impl = _ENGINES[engine](**kwargs)
        self.engine = engine

    def translate(
        self, text: str, src: str = "auto", tgt: str = "ar"
    ) -> TranslationResult:
        result = self.impl.translate(text, src=src, tgt=tgt)
        if isinstance(result, TranslationResult):
            return result
        # FinetunedTranslator يعيد str خامًا (كما في التصميم)
        return TranslationResult(str(result), self.engine, src, tgt)


# إضافة في Translator
from .languages import get_registry  # noqa: E402


class MultiLangTranslator:
    """مترجم يدعم لغات متعددة عبر عدة محركات."""

    def __init__(self, engine: str = "google", **kwargs):
        self.engine = engine
        self.registry = get_registry()
        self._cache = {}   # cache للـ backends حسب اللغة

        if engine == "google":
            from .translator import GoogleTranslator
            self.backend_cls = GoogleTranslator
        elif engine == "deepl":
            from .translator import DeepLTranslator
            self.backend_cls = DeepLTranslator
        elif engine == "hf":
            from .translator import HFTranslator
            self.backend_cls = HFTranslator
        else:
            raise ValueError(f"محرك غير معروف: {engine}")

    def _get_backend(self, tgt: str):
        """نموذج/backend خاص بكل لغة هدف (لـ hf)."""
        if self.engine != "hf":
            return self.backend_cls()

        if tgt in self._cache:
            return self._cache[tgt]

        model_id = self.registry.get_model_id(tgt, "marian")
        if not model_id:
            raise ValueError(f"لا يوجد نموذج لـ {tgt}")

        from .translator import HFTranslator
        backend = HFTranslator(model_name=model_id)
        self._cache[tgt] = backend
        return backend

    def translate(self, text: str, src: str = "auto",
                  tgt: str = "ar") -> "TranslationResult":
        from .translator import TranslationResult

        backend = self._get_backend(tgt)
        result = backend.translate(text, src=src, tgt=tgt)
        if isinstance(result, TranslationResult):
            return result
        return TranslationResult(str(result), self.engine, src, tgt)
