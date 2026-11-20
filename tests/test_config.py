# tests/test_config.py
"""اختبارات الإعدادات — ملفات yaml والبنية."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_config_yaml_loads():
    with open(ROOT / "config/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert isinstance(cfg, dict)


def test_config_required_sections():
    with open(ROOT / "config/config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for section in ("storage", "ocr", "telegram", "translation", "languages"):
        assert section in cfg, f"قسم مفقود: {section}"
    assert "download_dir" in cfg["storage"]
    assert "rules_file" in cfg["ocr"]


def test_config_example_exists():
    assert (ROOT / "config/config.example.yaml").exists()


def test_ocr_rules_file_has_18_rules():
    with open(ROOT / "config/marathon_ocr_rules.yaml", encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    ids = [r["id"] for r in rules["rules"]]
    assert len(rules["rules"]) == 18
    assert len(set(ids)) == 18, "تكرار في معرفات القواعد"
    # R01..R18 بالترتيب
    assert ids == [f"R{i:02d}" for i in range(1, 19)]


def test_ocr_rules_categories_covered():
    with open(ROOT / "config/marathon_ocr_rules.yaml", encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    categories = {r["category"] for r in rules["rules"]}
    assert {"cleanup", "substitution", "structure", "separation"} <= categories


# ملاحظة تدقيق (2026-10-03): كان هذا الاختبار يثبّت 10 لغات **بلا en** —
# أي أن غياب الإنجليزية كان قراراً مقصوداً ومُختبَراً (اسم الاختبار القديم:
# test_arabic_is_rtl_english_not_in_list). المراجعة نقضت القرار: en لغة المصدر
# في مسار TED، وغيابها يجعل /translate يرفض src="en" صراحةً ويجعل
# MultiLangTranslator يرفع ValueError. أُضيفت en بـ source_only: true وبلا
# نموذج marian، وحُدِّث العدّ إلى 11. هذا تغيير عقد مقصود، لا كسر عرضي.
def test_languages_yaml_has_11_languages_including_english():
    with open(ROOT / "config/languages.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    langs = data["languages"]
    assert len(langs) == 11
    assert "ar" in langs
    assert "en" in langs, "لغة المصدر مفقودة من السجل"
    for code, info in langs.items():
        assert "name" in info and "rtl" in info and "models" in info


def test_english_is_source_only_without_marian_model():
    """en لغة مصدر: لا نموذج marian لها، وإلا حُمّل نموذج غير موجود."""
    with open(ROOT / "config/languages.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    en = data["languages"]["en"]
    assert en["source_only"] is True
    assert en["rtl"] is False
    assert "marian" not in en["models"]


def test_arabic_is_rtl_and_has_marian_model():
    with open(ROOT / "config/languages.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    ar = data["languages"]["ar"]
    assert ar["rtl"] is True
    assert "marian" in ar["models"]


def test_registry_resolves_config_from_any_cwd(tmp_path, monkeypatch):
    """CONFIG_PATH يجب أن يكون مطلقاً — السبب الأول لإصلاح languages.py."""
    import os
    from src.languages import LanguageRegistry

    monkeypatch.chdir(tmp_path)          # CWD غريب تماماً
    monkeypatch.delenv("LANGUAGES_FILE", raising=False)
    reg = LanguageRegistry()
    assert "ar" in reg.list_all() and "en" in reg.list_all()
    assert os.path.isabs(str(reg.path)), "المسار ما زال نسبياً"


def test_registry_honours_languages_file_env(tmp_path, monkeypatch):
    """LANGUAGES_FILE يتجاوز المسار الافتراضي (للاختبار وللتوزيعات المخصصة)."""
    from src.languages import LanguageRegistry

    custom = tmp_path / "custom_langs.yaml"
    custom.write_text(
        "languages:\n  zz:\n    name: Zed\n    name_en: Zed\n    rtl: false\n"
        "    models:\n      google: zz\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANGUAGES_FILE", str(custom))
    reg = LanguageRegistry()
    assert reg.list_all() == ["zz"]
    assert reg.is_source_only("zz") is False


def test_gitignore_and_env_example_exist():
    assert (ROOT / ".gitignore").exists()
    assert (ROOT / ".env.example").exists()
