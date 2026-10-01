"""مثال: تجربة Google vs DeepL vs HF على 300 جملة."""
import requests
import hashlib

BASE = "https://marathon.example.com/api"
HEADERS = {"X-API-Key": "mrt_xxxx"}

# 1. إنشاء التجربة
r = requests.post(f"{BASE}/ab/experiments", headers=HEADERS, json={
    "name": "engine_comparison_v1",
    "description": "مقارنة 3 محركات على TED",
    "variants": [
        {"name": "google", "weight": 34},
        {"name": "deepl", "weight": 33},
        {"name": "hf", "weight": 33},
    ],
    "metric": "bleu",
})
print("إنشاء:", r.json())

# 2. ترجمة وتسجيل (لكل جملة)
sentences = [("Hello", "مرحبا"), ("World", "عالم")]
for src, ref in sentences:
    unit_id = hashlib.md5(src.encode()).hexdigest()[:16]

    # تخصيص
    variant = requests.post(f"{BASE}/ab/assign", headers=HEADERS, json={
        "experiment": "engine_comparison_v1",
        "unit_id": unit_id,
    }).json()["variant"]

    # ترجمة
    result = requests.post(f"{BASE}/translate", headers=HEADERS, json={
        "text": src, "src": "en", "tgt": "ar",
        "engine": variant,   # اختياري — لفرض المحرك
    }).json()

    # قياس
    score = requests.post(f"{BASE}/quality/evaluate", headers=HEADERS, json={
        "predictions": [result["translation"]],
        "references": [ref],
        "sources": [src],
    }).json()

    # سجّل
    requests.post(f"{BASE}/ab/results", headers=HEADERS, json={
        "experiment": "engine_comparison_v1",
        "unit_id": unit_id,
        "metric_value": score["bleu"],
    })

# 3. التحليل
r = requests.get(f"{BASE}/ab/experiments/engine_comparison_v1/analyze",
                 headers=HEADERS)
print("\nالتحليل:", r.json())
