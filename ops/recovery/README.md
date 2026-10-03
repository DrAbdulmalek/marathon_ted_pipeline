# ops/recovery — استعادة المشروع بعد إعادة ضبط بيئة التنفيذ

هذه الطبقة تُشغّل خط الجمع والرفع من الصفر على جهاز جديد/بيئة مُمسوحة.
كل بيانات الاعتماد تُقرأ من **متغيرات البيئة فقط** — لا شيء مكتوب داخل الكود
(نفس سياسة `collectors/16_telegram_upload.py`).

## المتغيرات المطلوبة

| المتغير | الوظيفة |
|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | بيانات التطبيق من my.telegram.org |
| `TELEGRAM_TARGET` | اسم القناة الهدف (مثل `DrMalekDrive`) |
| `TELEGRAM_SESSION` | مسار ملف الجلسة (اختياري، الافتراضي `mtp_upload`) |
| `TG_PHONE_FILE` / `TG_CODE_FILE` / `TG_PW_FILE` | ملفات واجهة الدخول (اختياري) |

⚠️ **لا تضع أبداً** ملف `.session` أو التوكنات أو رقم الهاتف في المستودع.
الجلسة = وصول كامل للحساب. نسخة الجلسة تُرسل لقناتك عبر السكريبت نفسه فقط.

## سيناريو الاستعادة الكامل (بيئة مُمسوحة)

```bash
# 0) استنساخ
git clone https://github.com/DrAbdulmalek/marathon_ted_pipeline.git
cd marathon_ted_pipeline
git checkout migrate/visual-evidence-charter   # يضم collectors/ + ops/recovery/

# 1) متغيرات البيئة
export TELEGRAM_API_ID=... TELEGRAM_API_HASH=... TELEGRAM_TARGET=DrMalekDrive

# 2) دمج قوائم الـ slugs (census + slugs_missing -> قائمة موحدة = 7,523)
python3 ops/recovery/merge_slug_lists.py

# 3) جمع الكوربس (en+ar، ~50 دقيقة، نجاح تاريخي ~85%)
python3 collectors/15_slug_campaign.py --langs en,ar --workers 8 --delay 0.3

# 4) بناء tar + الإحصائيات + الرفع للقناة عبر جلسة مصرّح بها
python3 ops/recovery/build_and_upload_corpus.py

# 5) إذا لم توجد جلسة مصرّح بها: دخول بالهاتف (رمز من تطبيق تيليجرام)
python3 ops/recovery/telegram_phone_upload.py
#    ثم اكتب الرمز في ملف tg_code.txt بجانب السكريبت
```

## ملاحظات تشغيلية (مُتحقَّق منها ميدانياً 2026-10-03)

1. `hls.ted.com/talks/{key}/subtitles/{lang}/full.vtt` يقبل **معرفاً أو slug**
   — البايتات متطابقة في الفضاءين (md5 متطابق للعينات المفحوصة).
2. المعرفات الحديثة (GraphQL) ميتة على hls — لذلك حملة الـ slug هي الأساس.
3. دمج `id_probe_talks_full.json` (census) مع `slugs_missing.json` يعطي
   **7,523 slug بالضبط** = التعداد الأصلي الكامل.
4. `phone_code_hash` لا يُحفظ في ملف الجلسة — الرمز القديم بلا تدفق حيّ
   `send_code_request` ملغى؛ أعد تشغيل سكريبت الدخول لإرسال رمز جديد.
5. في telethon 1.45: `qr.recreate()` يرجع `None` — استخدم `client.qr_login()`
   جديداً بدلاً منه.
6. ملفات الواجهة (`tg_phone.txt`, `tg_code.txt`, `tg_password.txt`) تُمسح
   محتواياً عند بدء الدخول وتُدار عبر الملفات — لا تمرر الرمز عبر argv.
