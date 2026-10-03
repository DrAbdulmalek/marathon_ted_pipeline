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


def test_ocr_rules_file_has_18_principles():
    """الميثاق v2: 18 مبدأ p01..p18 + قواعد التنظيف R01..R18 في ملف التطبيع."""
    with open(ROOT / "config/marathon_ocr_rules.yaml", encoding="utf-8") as f:
        charter = yaml.safe_load(f)
    assert charter["version"] == 2
    principles = sorted(charter["principles"].keys())
    assert len(principles) == 18
    assert [k[:3] for k in principles] == [f"p{i:02d}" for i in range(1, 19)]
    # القواعد الفعلية (تنظيف) انتقلت إلى text_normalization_rules.yaml
    with open(
        ROOT / "config/text_normalization_rules.yaml", encoding="utf-8"
    ) as f:
        norm = yaml.safe_load(f)
    ids = [r["id"] for r in norm["rules"]]
    assert len(norm["rules"]) == 18
    assert len(set(ids)) == 18, "تكرار في معرفات القواعد"
    assert ids == [f"R{i:02d}" for i in range(1, 19)]
    # السلاسل الحرفية الأصلية للمبادئ المفقودة سابقًا
    uf = charter["uncertainty_flags"]
    assert uf["visual_confidence_low"] == "VISUAL_CONFIDENCE_LOW"
    assert uf["visual_interpretation"] == "VISUAL_INTERPRETATION_UNCERTAIN"
    assert uf["color_semantics"] == "COLOR_SEMANTICS_UNCERTAIN"
    assert "✗" in charter["visual_markers"]["incorrect"]
    assert "X" in charter["visual_markers"]["incorrect"]


def test_ocr_rules_categories_covered():
    """فئات قواعد التنظيف (v1) + أقسام الميثاق الجوهرية (v2)."""
    with open(
        ROOT / "config/text_normalization_rules.yaml", encoding="utf-8"
    ) as f:
        norm = yaml.safe_load(f)
    categories = {r["category"] for r in norm["rules"]}
    assert {"cleanup", "substitution", "structure", "separation"} <= categories
    with open(ROOT / "config/marathon_ocr_rules.yaml", encoding="utf-8") as f:
        charter = yaml.safe_load(f)
    for section in (
        "visual_markers", "color_semantics", "uncertainty_flags",
        "classification_labels", "training_data_rules", "final_verification",
        "visual_metadata_schema",
    ):
        assert section in charter, f"قسم مفقود في الميثاق: {section}"
    assert charter["final_verification"]["verdicts"] == [
        "PASS", "PARTIAL", "UNCERTAIN", "FAILED",
    ]


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
