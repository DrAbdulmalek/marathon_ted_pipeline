# دليل المستخدم — Marathon TED Pipeline
**الإصدار:** 1.0.0 | **آخر تحديث:** 2025

---

## 📖 جدول المحتويات
1. مقدمة
2. البدء السريع
3. الواجهات المتاحة
4. المهام اليومية
5. حل المشاكل الشائعة
6. الأسئلة المتكررة

---

## 1. مقدمة

**Marathon TED Pipeline** نظام متكامل لـ:
- جلب ترجمات محادثات TED تلقائيًا
- معالجة مستندات PDF/EPUB بقواعد OCR دقيقة
- نشر الترجمات إلى تيليجرام و 3 أنظمة CMS
- ترجمة فورية لـ 10 لغات

**الجمهور المستهدف:**
- مسؤولو محتوى
- مترجمون ومحررون
- مطورون ومشرفون تقنيون

---

## 2. البدء السريع (5 دقائق)

### 2.1 الحصول على الوصول
اطلب من المدير:
- **API Key**: للنصوص والملفات
- **حساب Dashboard**: لعرض الإحصائيات
- **إذن البوت**: على تيليجرام

### 2.2 أول استدعاء API
```bash
curl -H "X-API-Key: mrt_xxxx" \
     https://marathon.example.com/api/health
```

2.3 أول استخدام للبوت

1. افتح Telegram
2. ابحث عن اسم البوت (اسأل المدير)
3. اضغط /start
4. جرّب /translate Hello world

---

3. الواجهات المتاحة

3.1 بوت تيليجرام (الأسهل)

الأمر الوظيفة
/start ترحيب
/help قائمة الأوامر
/status حالة النظام
/queue حالة المهام
/jobs آخر المهام
/rules قواعد OCR الحالية
/translate <نص> ترجمة فورية
/translate_to ar,fr <نص> ترجمة متعددة
/fetch <TED_URL> جلب محادثة
/langs عرض اللغات
أرسل PDF/EPUB معالجة ملف

أمثلة عملية:

مثال 1 — ترجمة فورية:

```
/translate Good morning, everyone!
→ صباح الخير للجميع!
```

مثال 2 — ترجمة متعددة:

```
/translate_to ar,fr,es Thank you
→ ar: شكرًا لك
   fr: Merci
   es: Gracias
```

مثال 3 — جلب محادثة TED:

```
/fetch https://www.ted.com/talks/xxx
→ ✅ تم جدولة المهمة
   🆔 Job: abc123...
```

مثال 4 — معالجة PDF:

```
[أرسل ملف document.pdf]
→ 📥 استلمت document.pdf
   ✅ تم استلام الملف
   🆔 Job: xyz789...
   
   (بعد دقائق)
   ✅ اكتملت المعالجة
   📄 document.pdf
   🏷️ التصنيف: POSITIVE_EXAMPLE, INCORRECT_EXAMPLE
   🎯 الثقة: medium
   [مرفق: document.md]
   [مرفق: document.meta.json]
```

3.2 لوحة التحكم (Dashboard)

الرابط: https://marathon.example.com

ما يمكنك فعله:

· 📊 عرض إحصائيات يومية
· 📁 مراجعة الملفات المعالجة
· 🧪 رفع PDF/EPUB مباشرة
· ⬇️ تنزيل النتائج

كيف تقرأ الرسوم البيانية:

· العمود الأخضر: عملية ناجحة
· العمود الأحمر: عملية فاشلة
· حجم Queue: عدد المهام في الانتظار
  · < 10: طبيعي
  · 10-50: مشغول
  · > 50: مرتكم — أبلغ المدير

3.3 واجهة API (للمطورين)

التوثيق التفاعلي: https://marathon.example.com/api/docs

Endpoint رئيسي:

```bash
# ترجمة نص
POST /api/translate
{
  "text": "Hello",
  "src": "en",
  "tgt": "ar"
}

# جلب TED
POST /api/ted/fetch
{
  "url": "https://www.ted.com/talks/...",
  "translate": true
}

# معالجة PDF (متزامن)
POST /api/ocr/pdf
[file upload]

# معالجة PDF (غير متزامن - للملفات الكبيرة)
POST /api/async/ocr/pdf
[file upload] → {job_id}

GET /api/async/jobs/{job_id} → حالة المهمة
```

3.4 Grafana (للمشرفين)

الرابط: https://marathon.example.com/grafana

لوحات رئيسية:

· الطلبات/ثانية: صحة عامة
· زمن الاستجابة: أداء
· معدل الأخطاء: يجب <1%
· Queue Depth: تراكم المهام

---

4. المهام اليومية

4.1 ترجمة مقال كامل

الطريقة 1 — بوت:

```
/translate <الصق النص>
```

الطريقة 2 — API:

```bash
curl -X POST https://marathon.example.com/api/translate \
  -H "X-API-Key: mrt_xxxx" \
  -H "Content-Type: application/json" \
  -d '{"text": "your text here", "tgt": "ar"}'
```

4.2 نشر ترجمة TED إلى المدونة

خطوة بخطوة:

1. /fetch https://www.ted.com/talks/xxx في البوت
2. انتظر إشعار الاكتمال
3. راجع الملف المُنزَّل
4. عدّل إذا لزم
5. انشر عبر CMS:

```bash
curl -X POST https://marathon.example.com/api/cms/publish \
  -H "X-API-Key: mrt_xxxx" \
  -d '{
    "cms_type": "wordpress",
    "title": "عنوان المقال",
    "content": "...",
    "tags": ["TED", "ترجمة"]
  }'
```

4.3 معالجة مجموعة PDF

1. افتح Dashboard
2. قسم "معالجة PDF مباشرة"
3. اسحب الملفات
4. انتظر النتائج
5. نزّل .md + .meta.json

4.4 مراجعة جودة ترجمة

عبر API:

```bash
curl -X POST https://marathon.example.com/api/quality/evaluate \
  -H "X-API-Key: mrt_xxxx" \
  -d '{
    "predictions": ["ترجمتك"],
    "references": ["الترجمة المرجعية"],
    "sources": ["النص الأصلي"]
  }'
```

النتيجة:

```json
{
  "bleu": 45.2,
  "chrf": 68.5,
  "meteor": 42.1,
  "overall": 52.3,
  "level": "good"
}
```

كيف تقرأ:

· ≥ 70: excellent — ممتازة
· 50-69: good — جيدة
· 30-49: fair — مقبولة
· < 30: poor — تحتاج مراجعة

---

5. حل المشاكل الشائعة

❌ "401 Unauthorized"

السبب: API Key خاطئ أو منتهي.
الحل:

1. تحقق من المفتاح (يبدأ بـ mrt_)
2. اطلب مفتاحًا جديدًا: /key <الاسم> في البوت

❌ "429 Too Many Requests"

السبب: تجاوزت الحد (10 req/s).
الحل: انتظر دقيقة، أو استخدم /async/... للملفات الكبيرة.

❌ "502 Bad Gateway"

السبب: الخدمة متوقفة.
الحل: أبلغ المدير فورًا.

❌ "الملف كبير جدًا"

الحد: 200MB.
الحل: استخدم /async/ocr/pdf بدل /ocr/pdf.

❌ "Bot لا يستجيب"

التحقق:

1. /status — هل البوت يرد؟
2. إذا لا: أبلغ المدير
3. إذا نعم لكن البطء: /queue لفحص التراكم

❌ "الترجمة سيئة"

الحلول:

1. جرّب محركًا آخر — اطلب من المدير تبديل engine
2. قسّم النص إلى جمل أقصر
3. استخدم /translate_to للمقارنة

❌ "الرموز ✓ ✗ مفقودة من PDF"

السبب: الصور غير واضحة أو Tesseract لم يتعرف عليها.
الحل:

1. جرّب PDF بدقة أعلى
2. أبلغ المدير لرفع dpi
3. راجع metadata.labels لمعرفة ما تم كشفه

---

6. الأسئلة المتكررة

س: هل النظام يدعم العربية فقط؟
ج: لا، يدعم 10 لغات: ar, fr, es, de, tr, fa, ur, zh, hi, ru.

س: هل يمكنني جدولة ترجمات يومية؟
ج: نعم، أبلغ المدير لإضافة cron أو استخدم GitHub Actions.

س: كيف أضمن جودة OCR؟
ج: استخدم PDF نصية (وليس ممسوحة)، بدقة ≥ 300 DPI.

س: هل الترجمة التلقائية معتمدة؟
ج: لا. راجعها دائمًا. النموذج مساعد لا بديل.

س: كيف أحتفظ بسجل عملياتي؟
ج: كل العمليات في data/logs/. اطلب من المدير نسخة.

س: هل يمكن استخدام النظام على الجوال؟
ج: نعم، عبر البوت أو Dashboard (استخدم متصفح جوال).

س: ماذا أفعل إذا نسيت كلمة المرور؟
ج: تواصل مع المدير لإعادة تعيينها.

س: هل يمكن تصدير الترجمات بصيغة معينة؟
ج: النظام ينتج SRT، JSON، Markdown. قابلة للتحويل لأي صيغة.

---

📞 التواصل والدعم

· Telegram: @marathon_support
· Email: support@example.com
· وثائق تقنية: /api/docs
· حالة النظام: https://status.example.com

---

📎 ملاحق

أ. جدول أوامر البوت الكامل

الأمر أمثلة
/translate /translate Hello
/translate_to /translate_to ar,fr,es Hi
/fetch /fetch <url>
/langs /langs
/status /status
/queue /queue
/jobs /jobs
/rules /rules
/key /key my-script (مدير)
/stats /stats (مدير)

ب. أيام العمل

الخدمة متاحة 24/7. للصيانة المجدولة، يُعلَن مسبقًا.

ج. الاستخدام العادل

· 10 req/s لكل API Key
· 1000 ترجمة/يوم للمستخدم العادي
· غير محدود للمدير

---

شكرًا لاستخدام Marathon TED Pipeline! 🎉
