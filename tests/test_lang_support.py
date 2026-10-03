# tests/test_lang_support.py
"""اختبارات دعم العربية-الإنجليزية — إصلاحات مراجعة DeepSeek (بلا شبكة)."""
import inspect
from pathlib import Path

import yaml

from src.languages import LanguageRegistry, get_registry
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


# ---------- الإصلاح 6: المسار الافتراضي مستقل عن CWD ----------
def test_default_registry_cwd_independent(tmp_path, monkeypatch):
    """LanguageRegistry() بالمسار الافتراضي يجب أن تعمل من أي دليل عمل.

    قبل الإصلاح كان CONFIG_PATH نسبيًا (config/languages.yaml) →
    FileNotFoundError فور الخروج من جذر المستودع. هذا الاختبار كان سيفشل
    قبل الإصلاح وهو قفله الانحداري.
    """
    monkeypatch.chdir(tmp_path)  # دليل بلا config/languages.yaml
    reg = LanguageRegistry()  # بلا مسار صريح — المسار الافتراضي بالضبط
    assert reg.get("en") is not None
    assert reg.is_rtl("ar") is True
    assert len(reg.list_all()) >= 11


def test_get_registry_singleton_from_foreign_cwd(tmp_path, monkeypatch):
    """get_registry() (المفرد) يعمل من CWD غريب ويعيد نفس المثيل."""
    monkeypatch.chdir(tmp_path)
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2
    assert r1.get("ar") is not None


# ---------- الإصلاح 5: source_lang في ted_fetcher ----------
def test_ted_fetch_exposes_source_lang():
    from src.ted_fetcher import TedFetcher

    sig = inspect.signature(TedFetcher.fetch)
    assert "target_lang" in sig.parameters
    assert "source_lang" in sig.parameters
    assert sig.parameters["source_lang"].default == "en"


# ---------- الإصلاح 7: CI lint يقبل الدَين القديم ويصطاد الأخطاء الحقيقية ----------
def test_ci_lint_selects_real_errors_only():
    """ci.yml يجب أن يفحص E9/F63/F7/F82 (أخطاء Python فعلية) لا الأسلوبيات.

    الدَين الأسلوبي القديم (344 بندًا على الفرع) كان سيجعل CI أحمر
    من أول تشغيل بلا أي إشارة مفيدة — التشديد التدريجي في PRs لاحقة.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff check src/ tests/ --select E9,F63,F7,F82" in ci
    # الحارس: لا نريد رجوعًا صامتًا للفحص الشامل المُغرِق
    bare = "run: ruff check src/ tests/\n"
    assert bare not in ci


# ---------- الإصلاح 8: مسارات config مستقلة عن CWD في api.py وdashboard.py ----------
def test_api_config_path_absolute_and_exists():
    """src.api.CONFIG_PATH مطلق ويشير لملف موجود — الافتراضي من موقع الوحدة."""
    import src.api as api_mod

    p = Path(api_mod.CONFIG_PATH)
    assert p.is_absolute(), f"يجب أن يكون مطلقًا: {p}"
    assert p.exists(), f"يجب أن يشير لملف موجود: {p}"
    # العقد البيئي القائم محفوظ (superset — لا كسر عقود نشر)
    api_text = (ROOT / "src/api.py").read_text(encoding="utf-8")
    assert 'os.getenv("CONFIG_PATH")' in api_text


def _subprocess_env(tmp_path):
    import os

    env = dict(os.environ)
    env.update({
        "AUTH_DB": str(tmp_path / "auth.db"),
        "AB_DB": str(tmp_path / "ab.db"),
        "WEBHOOK_DB": str(tmp_path / "webhooks.db"),
        "JWT_SECRET_KEY": "test_secret_key_for_pytest_only",
        "QUALITY_DB": str(tmp_path / "quality.db"),
        "PYTHONPATH": str(ROOT),
    })
    return env


def test_api_imports_from_foreign_cwd(tmp_path):
    """import src.api ينجح من دليل عمل خارج المستودع تمامًا (قبل الإصلاح: FileNotFoundError)."""
    import subprocess
    import sys

    env = _subprocess_env(tmp_path)
    env.pop("CONFIG_PATH", None)  # الافتراضي من موقع الوحدة — بلا تجاوز
    r = subprocess.run(
        [sys.executable, "-c", "import src.api; print('API_IMPORT_OK')"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
        check=False,  # نفحص stdout يدويًا — رسالة الفشل تحمل stderr كاملًا
    )
    assert "API_IMPORT_OK" in r.stdout, f"stderr={r.stderr[-2000:]}"


def test_api_config_path_env_contract(tmp_path):
    """عقد CONFIG_PATH البيئي ما زال يتفوق على الافتراضي (لا كسر عقود)."""
    import subprocess
    import sys

    probe = tmp_path / "config_probe.yaml"
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    cfg["__env_probe__"] = True
    probe.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    env = _subprocess_env(tmp_path)
    env["CONFIG_PATH"] = str(probe)
    r = subprocess.run(
        [sys.executable, "-c",
         "import src.api; print('PROBE:', src.api.CONFIG.get('__env_probe__'))"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
        check=False,  # نفس الدلالة — stdout يدويًا
    )
    assert "PROBE: True" in r.stdout, f"stderr={r.stderr[-2000:]}"


def test_dashboard_config_path_resolves_without_import():
    """dashboard.py غير قابل للاستيراد هنا (streamlit غير مثبت) — نفحص كوده نفسه عبر AST.

    نستخرج تعبير CONFIG_PATH الحقيقي من الملف ونقيّمه مع __file__ فعلي —
    هذا فحص للكود الحي لا لنسخة منه. لاحظ: dashboard.py في الجذر → parent واحدة.
    """
    import ast
    import os

    src_text = (ROOT / "dashboard.py").read_text(encoding="utf-8")
    assert 'os.getenv("MARATHON_CONFIG")' in src_text  # تجاوز النشر موجود
    tree = ast.parse(src_text)  # صلاحية syntax مجانًا
    assign = next(
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and getattr(n.targets[0], "id", None) == "CONFIG_PATH"
    )
    env = {"__file__": str(ROOT / "dashboard.py"), "os": os, "Path": Path}
    resolved = eval(compile(ast.Expression(assign.value), "<ast>", "eval"), env)
    resolved = Path(resolved)
    assert resolved.is_absolute(), f"يجب أن يكون مطلقًا: {resolved}"
    assert resolved.exists(), f"يجب أن يشير لملف موجود: {resolved}"
    # dashboard.py في الجذر: parent واحدة — لو استُخدمت parent.parent لخرج المسار خارج المستودع
    assert resolved.resolve().parent == (ROOT / "config").resolve()
