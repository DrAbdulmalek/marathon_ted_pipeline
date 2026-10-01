#!/bin/bash
# deploy/deploy.sh — نشر كامل على VPS جديد
set -euo pipefail

DOMAIN="${1:-marathon.yourdomain.com}"
EMAIL="${2:-admin@yourdomain.com}"
APP_DIR="/opt/marathon"

echo "🚀 بدء النشر على: $DOMAIN"

# ---------- 1. تحديث النظام ----------
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    curl wget git ufw \
    nginx certbot python3-certbot-nginx \
    apache2-utils \
    docker.io docker-compose-plugin

# ---------- 2. جدار الحماية ----------
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# ---------- 3. إنشاء المجلد ----------
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"
cd "$APP_DIR"

# ---------- 4. نسخ المشروع (عبر git أو scp) ----------
if [ ! -d ".git" ]; then
    echo "📂 انسخ ملفات المشروع إلى $APP_DIR يدويًا أو عبر git clone"
    echo "ثم أعد تشغيل السكربت."
    exit 1
fi

# ---------- 5. الإعدادات ----------
if [ ! -f "config/config.yaml" ]; then
    cp config/config.example.yaml config/config.yaml
    echo "⚠️ عدّل config/config.yaml قبل المتابعة"
    exit 1
fi

# ---------- 6. متغيرات البيئة ----------
if [ ! -f ".env" ]; then
    cat > .env <<EOF
JWT_SECRET_KEY=$(openssl rand -hex 32)
DEEPL_API_KEY=
APIFY_TOKEN=
REDIS_URL=redis://redis:6379/0
AUTH_DB=/app/data/auth.db
EOF
    echo "🔐 تم إنشاء .env"
fi

# ---------- 7. إعداد Nginx ----------
sudo cp deploy/nginx.conf /etc/nginx/sites-available/marathon
sudo sed -i "s/marathon.yourdomain.com/$DOMAIN/g" \
    /etc/nginx/sites-available/marathon

# Basic Auth للـ Dashboard
if [ ! -f /etc/nginx/.htpasswd ]; then
    sudo htpasswd -c /etc/nginx/.htpasswd admin
fi

sudo ln -sf /etc/nginx/sites-available/marathon \
    /etc/nginx/sites-enabled/marathon
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

# ---------- 8. شهادة SSL ----------
sudo certbot --nginx -d "$DOMAIN" \
    --non-interactive --agree-tos -m "$EMAIL" --redirect

# ---------- 9. بناء وتشغيل Docker ----------
sudo docker compose build
sudo docker compose up -d

# ---------- 10. مستخدم admin + API key ----------
sleep 10
sudo docker compose exec -T marathon_api python manage_auth.py \
    create-user admin "$(openssl rand -base64 12)" admin || true

echo ""
echo "✅ اكتمل النشر!"
echo "🌐 Dashboard: https://$DOMAIN"
echo "📚 API Docs: https://$DOMAIN/api/docs"
echo "🔑 لإدارة المستخدمين:"
echo "   docker compose exec marathon_api python manage_auth.py create-key 'my-script' admin"
