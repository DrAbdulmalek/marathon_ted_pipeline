# tests/test_lang_support.py
"""اختبارات دعم العربية-الإنجليزية — إصلاحات مراجعة DeepSeek (بلا شبكة)."""
import inspect
from pathlib import Path

import yaml

from src.languages import LanguageRegistry
from src.translator import (
    _DEFAULT_HF_MODELS,
    FinetunedTranslator,
    HFTranslator,
    TranslationResult,
)

ROOT = Path(__file__).resolve().parents[1]


# ---------- الإصلاح 1: en في languages.yaml ----------
def test_registry_defines_en():
    reg = LanguageRegistry(path=ROOT / "config/languages.yaml")
    assert reg.get("en") is not None
    assert "en" in reg.list_all()
    assert reg.list_all() == sorted(
        reg.list_all(), key=lambda c: (c != "en", c)
    ) or len(reg.list_all()) >= 11


def test_en_models_mapping():
    reg = LanguageRegistry(path=ROOT / "config/languages.yaml")
    en = reg.get("en")
    assert en["rtl"] is False
    assert en["models"]["google"] == "en"
    assert en["models"]["deepl"] == "EN"
    assert en["models"]["nllb"] == "eng_Latn"
    # بلا نموذج marian — get_model_id يعيد None بوضوح (فشل صادق لا خاطس)
    assert reg.get_model_id("en", "marian") is None


def test_rtl_flags():
    reg = LanguageRegistry(path=ROOT / "config/languages.yaml")
    assert reg.is_rtl("ar") is True
    assert reg.is_rtl("en") is False
    assert reg.is_rtl("fa") is True


# ---------- الإصلاح 2: عقد FinetunedTranslator ----------
def test_finetuned_signature_and_contract():
    sig = inspect.signature(FinetunedTranslator.__init__)
    assert "model_dir" in sig.parameters
    assert sig.parameters["src"].default == "en"
    assert sig.parameters["tgt"].default == "ar"
    tr_sig = inspect.signature(FinetunedTranslator.translate)
    assert tr_sig.return_annotation is TranslationResult


# ---------- الإصلاح 3: اختيار نموذج HF حسب الاتجاه ----------
def test_hf_model_selection_by_direction():
    assert _DEFAULT_HF_MODELS[("en", "ar")] == "Helsinki-NLP/opus-mt-en-ar"
    assert _DEFAULT_HF_MODELS[("ar", "en")] == "Helsinki-NLP/opus-mt-ar-en"
    t = HFTranslator()  # بلا تحميل — init كسول
    assert t._model_name_for("en", "ar") == "Helsinki-NLP/opus-mt-en-ar"
    assert t._model_name_for("ar", "en") == "Helsinki-NLP/opus-mt-ar-en"
    # اتجاه غير معروف → الافتراضي الآمن en→ar
    assert t._model_name_for("fr", "es") == "Helsinki-NLP/opus-mt-en-ar"
    # نموذج صريح يتجاوز الخريطة
    t2 = HFTranslator(model_name="custom/model")
    assert t2._model_name_for("ar", "en") == "custom/model"


# ---------- الإصلاح 4: مصدر حقيقة واحد للغات ----------
def test_config_yaml_no_duplicate_language_list():
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    asr_langs = cfg.get("asr", {}).get("languages", {})
    assert "supported" not in asr_langs, (
        "قائمة ميتة تضارب مع config/languages.yaml — يجب الحذف"
    )


# ---------- الإصلاح 5: source_lang في ted_fetcher ----------
def test_ted_fetch_exposes_source_lang():
    from src.ted_fetcher import TedFetcher

    sig = inspect.signature(TedFetcher.fetch)
    assert "target_lang" in sig.parameters
    assert "source_lang" in sig.parameters
    assert sig.parameters["source_lang"].default == "en"
