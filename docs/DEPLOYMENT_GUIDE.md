# دليل النشر الكامل — من VPS فارغ إلى نظام يعمل

## المتطلبات
- VPS: Ubuntu 22.04، 4 vCPU، 8GB RAM، 80GB SSD
- نطاق (domain) مُوجَّه إلى IP السيرفر
- حساب Telegram + bot
- 30-45 دقيقة

---

## المرحلة 1: تهيئة VPS (10 دقائق)

### 1.1 الاتصال بالسيرفر
```bash
ssh root@YOUR_VPS_IP
```

1.2 تحديث النظام وإنشاء مستخدم

```bash
apt update && apt upgrade -y
adduser marathon
usermod -aG sudo marathon
usermod -aG docker marathon
su - marathon
```

1.3 تثبيت Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version   # تحقق
```

1.4 جدار الحماية

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
sudo ufw status
```

1.5 ضبط التوقيت

```bash
sudo timedatectl set-timezone UTC
```

---

المرحلة 2: تحضير المشروع (5 دقائق)

2.1 استنساخ

```bash
cd /opt
sudo mkdir marathon && sudo chown $USER:$USER marathon
git clone <your-repo-url> marathon
cd marathon
```

2.2 إعداد الأسرار

```bash
cp .env.example .env
nano .env
```

املأ:

```
JWT_SECRET_KEY=<openssl rand -hex 32>
PG_PASSWORD=<كلمة قوية>
DEEPL_API_KEY=<اختياري>
APIFY_TOKEN=<اختياري>
TELEGRAM_BOT_TOKEN=<من @BotFather>
BOT_ADMINS=<chat_id الخاص بك>
GRAFANA_PASSWORD=<قوية>
```

توليد JWT:

```bash
openssl rand -hex 32
```

2.3 إعداد config.yaml

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

املأ:

```yaml
telegram:
  api_id: <من my.telegram.org>
  api_hash: "<من my.telegram.org>"
  target_channel: "@your_target_channel"
  source_channel: "@your_source_channel"
```

2.4 تسجيل الدخول لتليجرام (مرة واحدة)

```bash
docker compose run --rm marathon_app python -c "
from telethon import TelegramClient
import asyncio, yaml
with open('config/config.yaml') as f:
    cfg = yaml.safe_load(f)
async def login():
    c = TelegramClient('marathon_session',
                       cfg['telegram']['api_id'],
                       cfg['telegram']['api_hash'])
    await c.start()
    print('✅ تم تسجيل الدخول')
    await c.disconnect()
asyncio.run(login())
"
```

---

المرحلة 3: الإعداد الأولي (5 دقائق)

3.1 بناء الصور

```bash
docker compose build
```

3.2 تشغيل الخدمات الأساسية

```bash
docker compose up -d postgres redis
sleep 10
docker compose up -d
```

3.3 التحقق

```bash
docker compose ps
docker compose logs --tail=50 marathon_api
```

3.4 إنشاء مستخدم admin

```bash
docker compose exec marathon_api python manage_auth.py \
    create-user admin StrongPass123 admin
```

3.5 إنشاء API Key

```bash
docker compose exec marathon_api python manage_auth.py \
    create-key "main-script" admin
# انسخ المفتاح الناتج
```

---

المرحلة 4: النشر العام — Nginx + SSL (10 دقائق)

4.1 تثبيت Nginx و Certbot

```bash
sudo apt install -y nginx certbot python3-certbot-nginx apache2-utils
```

4.2 إعداد Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/marathon
sudo sed -i "s/marathon.yourdomain.com/YOUR_DOMAIN/g" \
    /etc/nginx/sites-available/marathon

# Basic Auth للـ Dashboard
sudo htpasswd -c /etc/nginx/.htpasswd admin

sudo ln -sf /etc/nginx/sites-available/marathon \
    /etc/nginx/sites-enabled/marathon
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
```

4.3 الحصول على شهادة SSL

```bash
sudo certbot --nginx -d YOUR_DOMAIN \
    --non-interactive --agree-tos -m your@email.com --redirect
```

4.4 إعادة تحميل Nginx

```bash
sudo systemctl reload nginx
```

---

المرحلة 5: ضمان الاستمرارية (5 دقائق)

5.1 systemd

```bash
sudo cp deploy/systemd/marathon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable marathon
sudo systemctl start marathon
sudo systemctl status marathon
```

5.2 Cron للنسخ الاحتياطي

```bash
crontab -e
```

أضف:

```
0 3 * * * /opt/marathon/deploy/backup.sh >> /var/log/marathon_backup.log 2>&1
0 4 * * 0 /opt/marathon/deploy/update.sh >> /var/log/marathon_update.log 2>&1
```

---

المرحلة 6: التحقق النهائي

6.1 اختبار كل خدمة

```bash
# API
curl https://YOUR_DOMAIN/api/health

# Dashboard
echo "افتح: https://YOUR_DOMAIN"

# Grafana
echo "افتح: https://YOUR_DOMAIN/grafana"

# Bot
echo "افتح Telegram → ابحث عن بوتك → /start"
```

6.2 اختبار مصادق

```bash
TOKEN=$(curl -X POST https://YOUR_DOMAIN/api/auth/token \
    -d "username=admin&password=StrongPass123" | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" \
    https://YOUR_DOMAIN/api/auth/me
```

6.3 اختبار رفع PDF

```bash
curl -X POST https://YOUR_DOMAIN/api/async/ocr/pdf \
    -H "X-API-Key: mrt_xxxxx" \
    -F "file=@test.pdf"
```

---

الصيانة الروتينية

يوميًا

```bash
docker compose ps
docker compose logs --since=24h | grep ERROR
```

أسبوعيًا

```bash
./deploy/update.sh
docker system prune -f
```

شهريًا

```bash
# تحقق من النسخ الاحتياطي
ls -lh /opt/marathon_backups/

# اختبار استعادة
tar -tzf /opt/marathon_backups/marathon_*.tar.gz | head
```

---

استكشاف الأخطاء

المشكلة: الحاويات لا تبدأ

```bash
docker compose logs marathon_api
docker compose down && docker compose up -d
```

المشكلة: SSL لا يعمل

```bash
sudo certbot renew --dry-run
sudo nginx -t
```

المشكلة: Bot لا يستجيب

```bash
docker compose logs marathon_bot
# تحقق من TELEGRAM_BOT_TOKEN في .env
```

المشكلة: queue متراكمة

```bash
docker compose logs marathon_worker
# زيادة replicas:
docker compose up -d --scale marathon_worker=4
```

---

نصائح أمنية نهائية

1. ✅ عطّل تسجيل الدخول بـ root عبر SSH
2. ✅ استخدم مفاتيح SSH فقط
3. ✅ فعّل fail2ban
4. ✅ حدّث النظام أسبوعيًا
5. ✅ احتفظ بنسخة احتياطية خارج السيرفر
6. ✅ راقب Grafana يوميًا
