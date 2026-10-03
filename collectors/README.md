# collectors/ — سكريبتات الجمع المستقلة

هذه طبقة الجمع الحية للمشروع. وفق القاعدة الذهبية للدمج المقترحة سابقًا:
**تستورد من `src/` ولا تنسخ منه** — حاليًا `ted_utils.py` مستقل عمدًا لأن
طبقة الجمع تعمل في بيئة منفصلة (بيئة الإنتاج للتجميع)، والدمج مع `src/`
منتظر قرار D-001.

## ملفات

| ملف | الوظيفة |
|---|---|
| `ted_utils.py` | الأداة المشتركة: تنزيل VTT من `hls.ted.com/talks/{key}/subtitles/{lang}/full.vtt` — `key` يقبل **معرفًا أو slug** (الفضاءان ينتجان بايتات متطابقة) |
| `01..12` في بيئة العمل | خط أنابيب الجمع الكامل (قائمة → تنزيل → تنظيف → رفع) |
| `02_download_subtitles.py` | حملة تنزيل بمعرفات؛ أضيف لها `--talks-file` لاختيار قائمة بديلة (مثل `talks_alive.json`) |
| `14_wayback_backfill.py` | استرجاع معرفات قديمة من Wayback Machine لشريحة 1,091 الميتة في الفضاءين — للجهاز الذي يصل إلى web.archive.org |
| `15_slug_campaign.py` | حملة الفضاء الجديد: تنزيل مباشر عبر slug بلا خريطة معرفات |
| `16_telegram_upload.py` | رفع المخرجات إلى القناة الهدف عبر Telethon (يقرأ بيانات الاعتماد من البيئة فقط) |

## الاكتشاف الحاسم (2026-10-03، بايتيًا)

1. `hls.ted.com` يعرض **فضاءين متكافئين**: `/talks/{id}/` و`/talks/{slug}/`
   — البايتات متطابقة (md5 متطابق لكل الأزواج المفحوصة: sir_ken slug==66،
   willard 1136 و1618).
2. المعرفات الحديثة (فضاء GraphQL `search.id` مثل 3292 لمحادثة sir_ken)
   **ميتة** على hls — كان هذا سبب بقاء التغطية عند 22%.
3. التعداد الكامل عبر slug لكل الـ 5,819 "المفقودة": **4,728 حية = 81.2%**
   → التغطية الإجمالية **6,432/7,523 = 85.5%** (en 6,423 + ar 6,355 ملفًا
   على القرص، 241MB).
4. المتبقي الميت في الفضاءين: **1,091 slug** — شريحة `14_wayback_backfill.py`.

## بيانات الدليل (مودعة في `data/`)

- `slugs_missing.json` — قائمة الـ 5,819 (مدخل حملة 15)
- `id_probe_talks_full.json` — تعداد فضاء المعرفات الكامل (2,038 → 1,667 حيًا)

## تشغيل سريع

```bash
python3 collectors/15_slug_campaign.py --langs en,ar --workers 5 --delay 0.5
python3 collectors/02_download_subtitles.py --talks-file data/talks_alive.json --langs en,ar
python3 collectors/16_telegram_upload.py corpus.tar.gz --caption "MTP corpus"
```
