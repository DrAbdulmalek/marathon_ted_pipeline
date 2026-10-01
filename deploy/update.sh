#!/bin/bash
# deploy/update.sh — تحديث المشروع بدون توقف طويل
set -euo pipefail

cd /opt/marathon

echo "📥 جلب آخر التحديثات..."
git pull

echo "🔨 إعادة بناء الصور..."
sudo docker compose build

echo "🔄 إعادة تشغيل تدريجية..."
sudo docker compose up -d --no-deps marathon_api marathon_monitor marathon_app
sleep 5
sudo docker compose up -d

echo "🧹 تنظيف الصور القديمة..."
sudo docker image prune -f

echo "✅ تم التحديث."
