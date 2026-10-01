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


def test_languages_yaml_has_10_languages():
    with open(ROOT / "config/languages.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    langs = data["languages"]
    assert len(langs) == 10
    assert "ar" in langs
    for code, info in langs.items():
        assert "name" in info and "rtl" in info and "models" in info


def test_arabic_is_rtl_english_not_in_list():
    with open(ROOT / "config/languages.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["languages"]["ar"]["rtl"] is True


def test_gitignore_and_env_example_exist():
    assert (ROOT / ".gitignore").exists()
    assert (ROOT / ".env.example").exists()
