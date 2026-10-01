#!/bin/bash
set -e

echo "🔧 تثبيت الاعتماديات..."
pip install -r finetune/requirements.txt

echo "📊 تحضير البيانات..."
python finetune/prepare_data.py

echo "🚀 التدريب..."
python finetune/train.py

echo "📈 التقييم..."
python finetune/evaluate.py

echo "✅ اكتمل! النموذج في: finetune/models/ted_ar_v1"
