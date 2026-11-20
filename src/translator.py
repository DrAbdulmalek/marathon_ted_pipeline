# src/translator.py
"""
محركات الترجمة:
- GoogleTranslator  (deep-translator)
- DeepLTranslator   (deepl REST)
- HFTranslator      (Helsinki-NLP / NLLB عبر transformers — تحميل كسول)
- FinetunedTranslator (نماذج مُدرَّبة محليًا على TED — finetune/) — يعيد TranslationResult
- MultiLangTranslator (10 لغات RTL/LTR عبر registry)
الواجهة الموحدة: translate(text, src, tgt) -> TranslationResult
"""
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
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
    """المحرك الثالث — نماذج MarianMT/NLLB محليًا (تحميل كسول).

    v2: اختيار النموذج حسب **زوج** اللغات ``(src, tgt)`` لا حسب ``tgt`` وحدها.
    السبب: النسخة السابقة كانت تثبّت ``Helsinki-NLP/opus-mt-en-ar`` دائماً،
    فكان ``translate(..., src="ar", tgt="en")`` يمرّر نصاً عربياً إلى نموذج
    إنجليزي←عربي ويُخرج هراءً — بلا خطأ ولا تحذير. هذا فشل صامت، وهو أخطر
    من الاستثناء.

    أولوية الاختيار:
      1. ``model_name`` صريح في الباني (سلوك قديم محفوظ حرفياً — لا يُتجاوز أبداً)
      2. جدول الأزواج :data:`PAIR_MODELS`
      3. سجل اللغات ``config/languages.yaml`` عبر ``get_model_id(tgt, "marian")``
      4. الافتراضي ``DEFAULT_MODEL`` مع تحذير مسجَّل
    """

    #: جدول أزواج اللغات الصريح. يُضاف إليه بدل تعديل المنطق.
    PAIR_MODELS = {
        ("en", "ar"): "Helsinki-NLP/opus-mt-en-ar",
        ("ar", "en"): "Helsinki-NLP/opus-mt-ar-en",
    }
    #: لغة المصدر الافتراضية عند ``src="auto"`` — مسار TED إنجليزي المصدر.
    AUTO_SRC = "en"
    DEFAULT_MODEL = "Helsinki-NLP/opus-mt-en-ar"

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        self.engine = "hf"
        #: None يعني "اختر حسب الزوج"؛ أي قيمة صريحة تُحترم دائماً.
        self._explicit_model = model_name
        self.model_name = model_name or self.DEFAULT_MODEL
        self._pipeline = None
        self._pipelines: dict = {}

    def select_model(self, src: str, tgt: str) -> str:
        """يعيد معرّف النموذج المناسب للزوج ``(src, tgt)``. دالة نقية قابلة للاختبار."""
        if self._explicit_model:
            return self._explicit_model
        s = (src or "auto").lower()
        if s in ("auto", "", "auto-detect"):
            s = self.AUTO_SRC
        t = (tgt or "ar").lower()
        pair_model = self.PAIR_MODELS.get((s, t))
        if pair_model:
            return pair_model
        # السجل: قد يملك نموذجاً للغة الهدف (مسار MultiLangTranslator)
        try:
            from .languages import get_registry

            reg_model = get_registry().get_model_id(t, "marian")
            if reg_model:
                self._warn_on_src_mismatch(reg_model, s, t)
                return reg_model
        except Exception as exc:            # السجل اختياري — لا يُفشل الترجمة
            logger.debug("تعذر الاستعلام من سجل اللغات: %s", exc)
        logger.warning(
            "لا نموذج معلناً للزوج (%s→%s) — يُستخدم الافتراضي %s. "
            "أضفه إلى HFTranslator.PAIR_MODELS أو config/languages.yaml.",
            s, t, self.DEFAULT_MODEL,
        )
        return self.DEFAULT_MODEL

    #: نمط معرّفات Marian: Helsinki-NLP/opus-mt-<src>-<tgt>
    _MARIAN_RE = re.compile(r"opus-mt-([a-z]{2,3}(?:-[a-z]{2,4})*)-([a-z]{2,3})$")

    @classmethod
    def _warn_on_src_mismatch(cls, model: str, src: str, tgt: str) -> None:
        """يحذّر بصوت عالٍ إن كان نموذج السجل مبنيّاً لمصدر مختلف.

        سجل اللغات يخزّن ``marian`` لكل لغة **هدف** بصيغة ``opus-mt-en-<tgt>``
        فقط. فطلب ``(ar→fr)`` كان يرجع نموذج ``en→fr`` ويترجم بصمت من المصدر
        الخطأ — نفس فئة الفشل الصامت التي يعالجها هذا الإصلاح. لا نمنع الطلب
        (قد يكون مقصوداً مع كشف اللغة)، لكن نجعله مرئياً في السجل.
        """
        m = cls._MARIAN_RE.search(model)
        if not m:
            return
        model_src = m.group(1)
        if model_src != src:
            logger.warning(
                "النموذج %s مبني للمصدر %s لكن الطلب src=%s (tgt=%s) — "
                "الترجمة قد تكون رديئة بصمت. أضف الزوج إلى HFTranslator.PAIR_MODELS.",
                model, model_src, src, tgt,
            )

    def _load(self, model_name: Optional[str] = None):
        """يحمّل (ويخزّن مؤقتاً) خط أنابيب لنموذج محدد.

        التخزين المؤقت **لكل نموذج** لا للنسخة كلها: مع اختيار النموذج حسب الزوج
        قد تتعاقب نماذج مختلفة داخل العملية نفسها، وإعادة التحميل لكل نص كانت
        ستكلف ثوانٍ لكل استدعاء.
        """
        name = model_name or self.model_name
        if name in self._pipelines:
            self._pipeline = self._pipelines[name]
            return self._pipeline
        from transformers import pipeline

        logger.info("تحميل نموذج HF: %s", name)
        pipe = pipeline("translation", model=name, device=-1)
        self._pipelines[name] = pipe
        self._pipeline = pipe          # توافق خلفي: كان يشير إلى الخط الوحيد
        self.model_name = name
        return pipe

    def translate(self, text: str, src: str = "auto", tgt: str = "ar") -> TranslationResult:
        if not text.strip():
            return TranslationResult("", self.engine, src, tgt)
        model = self.select_model(src, tgt)
        pipe = self._load(model)
        # تقسيم لقطات قصيرة (حد النماذج 512 توكن)
        chunks = [c for c in re.split(r"(?<=[.!؟?])\s+", text) if c.strip()]
        outs = []
        for chunk in chunks:
            res = pipe(chunk, max_length=512, truncation=True)
            outs.append(res[0]["translation_text"])
        return TranslationResult(" ".join(outs), self.engine, src, tgt,
                                 meta={"model": model})


# إضافة محرك رابع: fine-tuned
class FinetunedTranslator(BaseTranslator):
    #: المسار الافتراضي يُحلّ **نسبةً إلى جذر المستودع** لا إلى CWD — نفس فئة
    #: العطل التي أُصلحت في languages.py وocr_processor.py.
    DEFAULT_MODEL_DIR = "finetune/models/ted_ar_v1"

    def __init__(self, model_dir: Optional[str] = None):
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        import torch

        model_dir = model_dir or self.DEFAULT_MODEL_DIR
        candidate = Path(model_dir)
        if not candidate.is_absolute() and not candidate.exists():
            # CWD ليس جذر المستودع — جرّب المسار نسبةً إلى هذا الملف.
            from_repo = Path(__file__).resolve().parent.parent / model_dir
            if from_repo.exists():
                candidate = from_repo
        self.model_dir = str(candidate)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_dir).to(self.device)
        self.model.eval()
        self.engine = "finetuned-ted"

    def translate(self, text: str, src: str = "en", tgt: str = "ar") -> TranslationResult:
        """يعيد :class:`TranslationResult` — مطابقةً لعقد :class:`BaseTranslator`.

        كان يعيد ``str`` خاماً، وهو خرق لعقد الواجهة الموحدة (ومصدر خطأ mypy
        ``[override]``). ``Translator.translate`` و``MultiLangTranslator.translate``
        كانا يلفّان الناتج دفاعياً، فبقي الخرق مخفياً. اللفّ الدفاعي محفوظ
        هناك حتى لا ينكسر أي مستهلك قديم كان يعتمد على ``str``.
        """
        import torch
        if not text.strip():
            return TranslationResult("", self.engine, src, tgt)
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256,
        ).to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_length=256)
        text_out = self.tokenizer.decode(out[0], skip_special_tokens=True)
        return TranslationResult(
            text_out, self.engine, src, tgt,
            meta={"model_dir": self.model_dir, "device": self.device},
        )


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
        # لفّ دفاعي: كل المحركات الحالية تعيد TranslationResult (منذ إصلاح
        # FinetunedTranslator)، لكن أي محرك خارجي/قديم قد يعيد str فيُلفّ هنا
        # بدل أن ينفجر المستدعي. يُحفظ عمداً كطبقة توافق.
        logger.warning(
            "المحرك %s أعاد %s بدل TranslationResult — لُفّ آلياً. "
            "حدّث المحرك ليطابق عقد BaseTranslator.",
            self.engine, type(result).__name__,
        )
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
