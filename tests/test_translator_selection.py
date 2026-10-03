# tests/test_translator_selection.py
"""اختبارات إصلاحات src/translator.py (تدقيق 2026-10-03).

لا تحتاج transformers ولا torch ولا تنزيل نماذج: كل ما يُختبر هنا دوال نقية
(اختيار النموذج) أو عقود أنواع. هذا مقصود — الاختبار يجب أن يعمل في CI نفسه
الذي لا يحمّل نماذج.

ما تُثبته:
  1. HFTranslator يختار النموذج حسب **الزوج** (src, tgt) لا حسب tgt وحدها.
     قبل الإصلاح كان model_name مثبّتاً على opus-mt-en-ar دائماً، فكان
     ar→en يمرّر نصاً عربياً لنموذج إنجليزي←عربي ويُخرج هراءً **بلا خطأ**.
  2. model_name الصريح يُحترم دائماً (توافق خلفي — لا يُكسر مستهلك قائم).
  3. نموذج السجل المبني لمصدر مختلف يُحذَّر منه ولا يمر بصمت.
  4. FinetunedTranslator.translate مطابقة لعقد BaseTranslator (TranslationResult).
  5. اللفّ الدفاعي في Translator ما زال يحوّل str إلى TranslationResult.
"""
from __future__ import annotations

import inspect
import logging

import pytest

from src.translator import (
    BaseTranslator,
    HFTranslator,
    TranslationResult,
    Translator,
)


# ---------------------------------------------------------------------------
# 1) اختيار النموذج حسب الزوج
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "src,tgt,expected",
    [
        ("en", "ar", "Helsinki-NLP/opus-mt-en-ar"),
        ("ar", "en", "Helsinki-NLP/opus-mt-ar-en"),   # كان مستحيلاً قبل الإصلاح
        ("auto", "ar", "Helsinki-NLP/opus-mt-en-ar"),  # AUTO_SRC = en
        ("EN", "AR", "Helsinki-NLP/opus-mt-en-ar"),    # لا حساسية لحالة الأحرف
    ],
)
def test_pair_table_selects_the_right_model(src, tgt, expected):
    assert HFTranslator().select_model(src, tgt) == expected


def test_unknown_pair_falls_back_to_default():
    """زوج بلا نموذج معلَن → الافتراضي (مع تحذير)، لا استثناء."""
    t = HFTranslator()
    assert t.select_model("zz", "yy") == HFTranslator.DEFAULT_MODEL


def test_registry_supplies_target_language_model():
    """(en→fr) غير موجود في الجدول فيُجلب من config/languages.yaml."""
    assert HFTranslator().select_model("en", "fr") == "Helsinki-NLP/opus-mt-en-fr"


# ---------------------------------------------------------------------------
# 2) التوافق الخلفي: model_name الصريح لا يُتجاوز
# ---------------------------------------------------------------------------

def test_explicit_model_name_always_wins():
    t = HFTranslator(model_name="my/custom-model")
    for src, tgt in (("en", "ar"), ("ar", "en"), ("zz", "yy")):
        assert t.select_model(src, tgt) == "my/custom-model"
    # والحقل القديم ما زال مكشوفاً لمن كان يقرأه
    assert t.model_name == "my/custom-model"


def test_select_model_is_pure_and_needs_no_transformers():
    """select_model يجب ألا يستورد transformers (وإلا صار الاختبار بطيئاً/هشاً)."""
    src = inspect.getsource(HFTranslator.select_model)
    assert "transformers" not in src


# ---------------------------------------------------------------------------
# 3) الفشل الصامت يصبح مرئياً
# ---------------------------------------------------------------------------

def test_source_mismatch_is_warned_not_silent(caplog):
    """(ar→fr) يرجع نموذج en-fr من السجل — يجب أن يُحذَّر منه صراحةً."""
    with caplog.at_level(logging.WARNING, logger="src.translator"):
        model = HFTranslator().select_model("ar", "fr")
    assert model == "Helsinki-NLP/opus-mt-en-fr"
    assert any("مبني للمصدر" in r.getMessage() for r in caplog.records), \
        [r.getMessage() for r in caplog.records]


def test_matching_source_is_not_warned(caplog):
    """لا تحذير عندما يتطابق مصدر النموذج مع src المطلوب (لا ضجيج بلا سبب)."""
    with caplog.at_level(logging.WARNING, logger="src.translator"):
        HFTranslator().select_model("en", "fr")
    assert not [r for r in caplog.records if "مبني للمصدر" in r.getMessage()]


def test_warn_helper_detects_marian_pattern():
    f = HFTranslator._warn_on_src_mismatch
    # نمط Marian يُقرأ صح، وغير Marian يُتجاهل بلا انهيار
    assert HFTranslator._MARIAN_RE.search("Helsinki-NLP/opus-mt-en-fr")
    assert HFTranslator._MARIAN_RE.search("Helsinki-NLP/opus-mt-ar-en")
    assert HFTranslator._MARIAN_RE.search("facebook/nllb-200") is None
    assert callable(f)


# ---------------------------------------------------------------------------
# 4) عقد النوع: FinetunedTranslator
# ---------------------------------------------------------------------------

def test_finetuned_translate_is_annotated_as_translation_result():
    """العقد مُعلن في التوقيع — لا نحتاج torch للتحقق منه."""
    from src.translator import FinetunedTranslator

    hints = inspect.signature(FinetunedTranslator.translate).return_annotation
    assert hints in (TranslationResult, "TranslationResult"), hints


def test_base_and_finetuned_return_annotations_agree():
    """خرق LSP كان مصدر خطأ mypy [override] — التوقيعان الآن متطابقان."""
    from src.translator import FinetunedTranslator

    base = inspect.signature(BaseTranslator.translate).return_annotation
    fine = inspect.signature(FinetunedTranslator.translate).return_annotation
    assert base == fine


def test_every_engine_class_declares_translation_result():
    from src import translator as tr

    for name, cls in tr._ENGINES.items():
        ann = inspect.signature(cls.translate).return_annotation
        assert ann in (TranslationResult, "TranslationResult"), f"{name}: {ann}"


# ---------------------------------------------------------------------------
# 5) اللفّ الدفاعي ما زال يعمل (superset لا كسر)
# ---------------------------------------------------------------------------

class _LegacyStrTranslator(BaseTranslator):
    """محاكاة محرك قديم/خارجي ما زال يعيد str."""

    engine = "legacy"

    def translate(self, text: str, src: str = "auto", tgt: str = "ar"):
        return f"translated:{text}"


def test_translator_wraps_legacy_str_result(monkeypatch):
    from src import translator as tr

    monkeypatch.setitem(tr._ENGINES, "legacy", _LegacyStrTranslator)
    t = Translator(engine="legacy")
    out = t.translate("hello", src="en", tgt="ar")
    assert isinstance(out, TranslationResult)
    assert out.translated_text == "translated:hello"
    assert out.engine == "legacy" and out.src == "en" and out.tgt == "ar"


def test_translation_result_defaults_are_stable():
    r = TranslationResult("x")
    assert r.meta == {} and r.engine == "google" and r.src == "auto" and r.tgt == "ar"
    r2 = TranslationResult("y", "hf", "en", "fr", meta={"model": "m"})
    assert r2.meta == {"model": "m"}
