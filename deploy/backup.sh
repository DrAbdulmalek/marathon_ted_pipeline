#!/bin/bash
# deploy/backup.sh — نسخ احتياطي يومي
set -euo pipefail

BACKUP_DIR="/opt/marathon_backups"
APP_DIR="/opt/marathon"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# نسخ compressed لكل شيء ما عدا المجلدات الثقيلة
cd "$APP_DIR"
tar --exclude='data/downloads' \
    --exclude='node_modules' \
    --exclude='.venv' \
    -czf "$BACKUP_DIR/marathon_$DATE.tar.gz" \
    config/ data/logs/ data/auth.db .env docker-compose.yml

# نسخ PostgreSQL
docker compose exec -T postgres pg_dump -U ted ted2srt | \
    gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz"

# حذف النسخ الأقدم من 30 يومًا
find "$BACKUP_DIR" -type f -mtime +30 -delete

echo "✅ نسخة احتياطية: $BACKUP_DIR/marathon_$DATE.tar.gz"
