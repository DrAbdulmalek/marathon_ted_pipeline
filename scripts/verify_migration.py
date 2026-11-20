# scripts/verify_migration.py
"""تحقق ما بعد ترحيل ميثاق الدليل البصري — قائمة DeepSeek الحرفية."""
import sys

sys.path.insert(0, ".")

from src.ocr_pipeline import OCRPipeline
from src.ocr_processor import OCRProcessor

p = OCRProcessor("config/marathon_ocr_rules.yaml")

# 1) السلاسل الحرفية التي كانت مفقودة
incorrect = p.visual_markers_cfg["incorrect"]
assert "✗" in incorrect, "✗ missing!"
assert "✘" in incorrect, "✘ missing!"
assert "X" in incorrect, "X missing!"
assert "☑" in p.visual_markers_cfg["correct"], "☑ missing!"

# 2) حالات عدم اليقين
r = p.apply_visual_rules("t", {"detected": ["X"]})
assert r["x_warning"] == "X_REQUIRES_CONTEXT_CHECK", r

c = p.detect_color_with_legend("plain", [{"rgb": (200, 30, 40), "text": "r"}])
assert c["label"] == "COLOR_SEMANTICS_UNCERTAIN", c

# 3) التحقق النهائي الكامل (11 فحصًا)
checks = p.verification["required_checks"]
assert len(checks) == 11, len(checks)
fv = p.final_verify({c_: True for c_ in checks})
assert fv["verdict"] == "PASS"

# 4) التوافق الخلفي: process_text v1 يعمل عبر الميثاق (تحميل تلقائي)
res = p.process_text("مرحبا\u200b بالعالم ٢٠٢٥ ✔")
assert "\u200b" not in res["markdown"], "R01 فشل عبر التحميل التلقائي"
assert "2025" in res["markdown"], "R10 فشل عبر التحميل التلقائي"
assert res["metadata"]["rules_applied"], "لا قواعد سُجلت"

# 5) خط الأنابيب ذو الطبقتين
pipe = OCRPipeline()
out = pipe.process_text(
    "The correct translation is here ✓ but this one is wrong ✗",
    detected_markers=["✓", "✗"],
    detected_colors=[{"rgb": (200, 30, 40), "text": "bad", "page": 1}],
)
assert out["visual"]["status"] == "uncertain", out["visual"]
assert out["color"]["label"] == "COLOR_SEMANTICS_UNCERTAIN"
assert out["context"]["dominant"] == "mixed", out["context"]
assert "correct translation" in out["normalized_text"]

# 6) build_metadata = حقول v1 + v2
md = p.build_metadata(source_type="pdf", page=1, image_index=0,
                      ocr_text="x", visual_status="neutral")
for k in ("rules_file", "word_ratio", "source_type", "visual_status",
          "visual_marker", "color_status", "confidence"):
    assert k in md, k

# 7) ملف التنظيف v1 ما زال يعمل كالمستقل
norm = OCRProcessor("config/text_normalization_rules.yaml")
res2 = norm.process_text("السنة ٢٠٢٥")
assert "2025" in res2["markdown"]

print("ALL-MIGRATION-CHECKS-PASSED")
print("version:", p.version)
print("normalization_file:", p.normalization_file)
print("incorrect markers:", incorrect)
print("11 checks:", checks[:3], "...")
