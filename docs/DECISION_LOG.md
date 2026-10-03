# سجل القرارات — Marathon TED Pipeline

## D-001: تأجيل دمج `migrate/visual-evidence-charter` إلى main

**التاريخ:** 2026-10-03
**الحالة:** مُؤجَّل (Deferred)
**المُقرِّر:** DrAbdulmalek
**المرجع:** فرع `migrate/visual-evidence-charter` (ستة التزامات، آخرها `b933cd2` —
وهذا السجل نفسه هو الالتزام السابع)

### السياق

فرع الترحيل يحوي ستة التزامات تُصلح:

1. `src/ocr_processor.py` — إعادة كتابة كـ superset يحفظ عقود v1 ويضيف
   ميثاق الدليل البصري v2 (الرموز ✓ ✔ ✗ ✘ X x ✖ ❌ ☑، حالات عدم اليقين
   COLOR_SEMANTICS_UNCERTAIN / VISUAL_INTERPRETATION_UNCERTAIN /
   VISUAL_CONFIDENCE_LOW، تصنيفات EXAMPLE_OF_ERROR / INCORRECT_EXAMPLE /
   VISUAL_CORRECTION_EXAMPLE / POSITIVE_EXAMPLE، مخطط metadata البصري،
   فصل training_data positive_example ≠ negative_example).

2. `config/marathon_ocr_rules.yaml` — استبدال v1 التنظيفي بـ v2 الميثاقي.
   v1 محفوظ كـ `config/text_normalization_rules.yaml` كمرحلة pre-pass.

3. `src/languages.py` — إصلاح `CONFIG_PATH` من نسبي إلى مطلق (استقلال
   عن CWD) + تجاوز بـ `LANGUAGES_FILE`. تم تعميم النمط على `src/api.py`
   (مع حفظ عقد `CONFIG_PATH` البيئي القائم) و`dashboard.py` (مسار جذر
   بـ `.parent` واحدة) في الالتزامين 6eaf79f و a55ae55.

4. `.github/workflows/ci.yml` — `ruff check --select E9,F63,F7,F82`
   (تجاوز 344 خطأ أسلوبي موروث، مع الحفاظ على كشف الأخطاء الفعلية).

5. `data/evidence/talk_8593_ar.vtt` — fixture دائم (16,710 B) + 3 اختبارات
   قفل (حجم ≥16KB، بنية WEBVTT، >500 حرف عربي) تمنع الاستبدال الصامت.

6. اختبارات إضافية: 94 passed / 1 skipped (من 61/1 أصلي).

### سبب التأجيل

الدمج إلى main يُفعّل:
- `build-and-push` (بناء صورة Docker ونشرها على GHCR)
- `security-scan` (Trivy)
- تفعيل الالتزام بتشغيل الخدمات (compose up، workers، إلخ)

هذه الالتزامات **لم تُختبَر بعد في بيئة حقيقية**:
- لا Docker في بيئة التطوير الحالية
- لا Redis للتشغيل الحي
- لا E2E كامل (PDF + tesseract + رفع فعلي)

دمج كود غير مُختبَر وظيفيًا = مخاطرة إنتاجية غير مبررة.

### شروط رفع التأجيل

يُرفع التأجيل عند تحقق **كل** ما يلي:

- [ ] PR مفتوح ويُظهر CI أخضر على `lint-and-test`
- [ ] مراجعة بشرية للـ diff (اقرأ الأسطر، لا المؤشرات الخضراء)
- [ ] `docker compose config` يمر بنجاح على جهاز حقيقي
- [ ] `docker compose up -d` يقلع كل الخدمات (12 خدمة — مُتحقق منها
      بقراءة docker-compose.yml فعليًا)
- [ ] اختبار E2E واحد: PDF فيه ✓/✗ → معالجة → فحص metadata.labels
      ينتج POSITIVE_EXAMPLE و INCORRECT_EXAMPLE
- [ ] `curl https://<domain>/api/health` يعيد 200
- [ ] Bot يردّ على `/start` و `/rules` و `/translate hello`

### الحالة الحالية لكل فرع

| الفرع | آخر commit | الحالة | معلَّق |
|-------|-----------|--------|---------|
| `main` | `7e90498` | عذراء (untouched) | — |
| `migrate/visual-evidence-charter` | `b933cd2` + هذا السجل | جاهز للـ PR | شرط الرفع أعلاه |
| `audit/visual-evidence-rules` | (قديم) | مهمل | يحتاج إعادة تقييم بعد الدمج |

### ما لا يفعله هذا القرار

- لا يحذف الفرع
- لا يعيد تغيير main
- لا يمنع مواصلة العمل على الفرع
- لا يُلزم بجدول زمني

### المراجعة التالية

بعد أول `gh pr checks` نجاح. عندها يُحدَّث هذا السجل بـ:
- نتيجة CI الفعلية
- قائمة المشاكل التي كشفها الـ PR
- قرار الدمج أو مزيد من التأجيل

---

## ملحق أ (2026-10-03): أدلة تعداد المعرفات — بعد القرار

أُجري مسح كامل (تعداد لا استقراء) لنقطة `hls.ted.com` أثناء تحضير PR،
النتائج ملفّة في خارج المستودع (`id_probe_results.json`,
`id_probe_talks_path.json`) وتُلخَّص هنا لأنها تغيّر حسابات حملة الجمع:

| المسار | الحية (معرفات فريدة) | ملاحظة |
|--------|----------------------|--------|
| `project_masters/{id}/subtitles/{lang}/full.vtt` | 1,530 | من 2,038 معرفًا < 20k (1,563 مدخل محادثة — 33 معرفًا مشتركًا بين slug‑s) |
| `talks/{id}/subtitles/{lang}/full.vtt` (صيغة بديلة مكتشفة) | +243 | أحيَت 247 من أصل 475 معرفًا ميتًا في المسار الأول |
| **الاتحاد** | **1,773 (23.6%)** | السقف العملي المؤكد بايتيًا من أصل 7,523 |

- محتوى المسارين لمعرف حي **مختلف بايتيًا** (1136: ‏10,710B vs 10,511B،
  md5 مختلف) — مساران لنسختين مختلفتين، لا مجرد alias.
- النطاقات ≥ 20k (المعرفات الحديثة tedx_dataset): ميتة في الصيغتين (0/16 عينات) —
  فجوة slug→ID ما تزال مفتوحة لـ 5,750 محادثة.
- `api.ted.com/v1` **حي** (يرد 500 "invalid API key" — خطأ مصادقة، ليس حجب ASN)
  بخلاف `www.ted.com` (403). مفتاح صالح قديم قد يفتح خريطة slug→ID.
- 37 تصادم معرف (نفس الرقم لـ slug مختلفين عبر مزج المصادر) — صفر التباس
  داخلي في willard نفسه؛ الشركاء من tedx_dataset معرفاتهم تحتاج حلًّا مستقلًا.

**الأثر على شروط الرفع**: لا يغيّرها. لكنه يعني أن أول حملة جمع E2E
على 1,773 معرفًا حيًّا ممكنة فور دمج الفرع، بلا طلبات مهدورة.
