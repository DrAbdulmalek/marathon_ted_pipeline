# 🏃 Marathon TED Pipeline

منصة إنتاجية كاملة من A إلى Z: استخراج وترجمة ونشر المحتوى — TED / PDF / EPUB / ASR / تيليجرام / CMS — جاهزة للاستخدام التجاري الفوري.

**الإصدار:** 1.0.0

---

## 📦 ما تم تسليمه إجمالًا

| # | المجال | المخرجات |
|---|--------|----------|
| 1 | OCR | قواعد 18 بند + PDF + EPUB + كشف رموز/ألوان |
| 2 | TED | 3 أنماط جلب + ted2srt-py محلي |
| 3 | ترجمة | 4 محركات + 10 لغات + RTL/LTR |
| 4 | ASR | Whisper محلي/API + Vosk + خط أنابيب كامل |
| 5 | تيليجرام | مراقب + رافع + بوت متكامل |
| 6 | API | FastAPI + JWT + API Keys + Webhooks |
| 7 | CMS | WordPress + Notion + Webhook عام |
| 8 | جودة | BLEU/chrF/METEOR/COMET/BERTScore |
| 9 | A/B Testing | تجارب + t-test + اختيار تلقائي |
| 10 | Queue | Redis + RQ + Workers |
| 11 | مراقبة | Prometheus + Grafana + Alerts |
| 12 | نشر | Docker Compose + Kubernetes |
| 13 | بوابة | Nginx + SSL + Rate Limiting |
| 14 | CI/CD | 5 GitHub Actions workflows |
| 15 | تدريب | Fine-tune MarianMT على TED |
| 16 | توثيق | دليل مستخدم PDF + تقني + معمارية |
| 17 | اختبارات | 8 ملفات pytest (~50 اختبار) |
| 18 | تجاري | SLA + Pricing + Case Studies |

---

## 🚀 خطوات البدء الفعلي

```bash
# 1. استنساخ
git clone <repo> marathon && cd marathon

# 2. تهيئة
cp .env.example .env && nano .env
cp config/config.example.yaml config/config.yaml && nano config/config.yaml

# 3. نشر بنقرة
./deploy/deploy.sh yourdomain.com admin@email.com

# 4. اختبار
curl https://yourdomain.com/api/health
```

### خيارات النشر

**الخيار A — Docker Compose (الأبسط):**

```bash
./deploy/deploy.sh marathon.yourdomain.com admin@email.com
```

**الخيار B — Kubernetes (للتوسع):**

```bash
kubectl apply -k k8s/overlays/production/
kubectl -n marathon get pods -w
```

### إدارة المستخدمين والمفاتيح

```bash
# مستخدم admin
docker compose exec marathon_api python manage_auth.py \
    create-user admin StrongPass123 admin

# مفتاح API لسكربت
docker compose exec marathon_api python manage_auth.py \
    create-key "my-script" user
```

---

## 🧪 الاختبارات

```bash
pip install -r requirements.txt
pytest
```

> ملاحظة: الاختبارات الثقيلة (Redis queue، نماذج ASR الكاملة) تتخطى نفسها تلقائيًا عند غياب الخدمة.

---

## 🎁 الميزات الفريدة التي تميّز النظام

- 🔐 معالجة محلية — كل شيء على سيرفرك
- 🎯 فصل صحيح/خاطئ في OCR — لا تضليل نماذج التدريب
- 📊 A/B Testing مدمج لاختيار أفضل محرك
- 🌐 ASR + OCR + ترجمة في منصة واحدة
- 🔗 Webhooks موقّعة HMAC للتكامل الآمن
- ☸️ HPA-Ready — يتوسع تلقائيًا حتى 20 worker
- 📈 مراقبة كاملة مع تنبيهات Telegram
- 🎓 Fine-tuning مخصص على بيانات TED
- 💰 نموذج تجاري واضح مع 3 خطط + خدمات إضافية

---

## 📂 البنية

```
marathon_ted_pipeline/
├── config/            # config.yaml + marathon_ocr_rules.yaml (18 قاعدة) + languages.yaml
├── src/               # api, auth, queue_worker, ocr/pdf/epub, ted_fetcher,
│   │                  # translator (4 محركات), cms/, quality/, asr/, ab_testing,
│   │                  # webhooks, telegram_bot, channel_monitor, uploader, metrics
├── ted2srt_py/        # خدمة TED المحلية (Flask :3002)
├── deploy/            # nginx.conf + deploy.sh + update.sh + backup.sh + systemd
├── monitoring/        # Prometheus + Grafana + Alertmanager
├── k8s/               # Kustomize (base + overlays/production)
├── finetune/          # تدريب نماذج ترجمة مخصصة
├── docs/              # USER_MANUAL + DEPLOYMENT_GUIDE + ARCHITECTURE + SLA + PRICING
├── tests/             # 8 ملفات pytest
├── examples/          # webhook_receiver + run_ab_experiment + transcribe_ted
├── .github/           # 5 workflows + dependabot
├── docker-compose.yml # 12 خدمة
├── Dockerfile
└── requirements.txt
```

---

## 💰 مسارات الاستثمار

1. تشغيله محليًا للاستخدام الشخصي
2. نشره تجاريًا مع خطة Pricing (docs/PRICING.md)
3. بيعه كـ White Label لشركات ($25K)
4. تقديمه SaaS مع خطط اشتراك
5. تدريب نماذج مخصصة لعملاء آخرين

---

## 📚 التوثيق

- **قواعد العمل الرسمية (حاكم):** docs/RULES.md — ميثاق OCR (1–18) + القواعد الميدانية المكتسبة من التنفيذ
- **دليل المستخدم:** docs/USER_MANUAL.md (PDF: `bash docs/build.sh`)
- **دليل النشر:** docs/DEPLOYMENT_GUIDE.md
- **المخطط المعماري:** docs/ARCHITECTURE.md
- **عقد SLA:** docs/SLA_TEMPLATE.md
- **خطة التسعير:** docs/PRICING.md
- **الاستعادة بعد إعادة ضبط البيئة:** ops/recovery/README.md
