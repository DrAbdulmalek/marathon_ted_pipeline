# src/api.py
"""
REST API — FastAPI:
- معالجة PDF/EPUB (متزامن + غير متزامن عبر Queue)
- جلب وترجمة TED
- مصادقة مزدوجة (API Key + JWT)
- Webhooks موقّعة HMAC
- تكامل CMS + تقييم جودة + A/B Testing + ASR
- مقاييس Prometheus
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- الإعدادات ----------
# المسار مستقل عن CWD: الافتراضي مشتق من موقع الوحدة، والعقد البيئي القائم
# CONFIG_PATH محفوظ كما هو (superset — لا كسر عقود نشر قائمة)
CONFIG_PATH = Path(
    os.getenv("CONFIG_PATH")
    or Path(__file__).resolve().parent.parent / "config" / "config.yaml"
)
with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

app = FastAPI(
    title="Marathon TED Pipeline API",
    version="1.0.0",
    description="استخراج وترجمة ونشر المحتوى — TED/PDF/EPUB/ASR",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- المصادقة ----------
from .auth import (  # noqa: E402
    User, get_current_user, require_admin, Token,
    verify_user, create_access_token, init_db,
)

init_db()


# ---------- نماذج الطلبات ----------
class TedRequest(BaseModel):
    url: str
    translate: bool = False
    target_lang: str = "ar"


class TranslateRequest(BaseModel):
    text: str
    src: str = "auto"
    tgt: str = "ar"


class WebhookCreate(BaseModel):
    url: str
    secret: str
    events: List[str] = ["*"]


class PublishRequest(BaseModel):
    cms_type: str
    title: str
    content: str
    tags: List[str] = []


class QualityRequest(BaseModel):
    predictions: List[str]
    references: List[str]
    sources: Optional[List[str]] = None


class ExperimentCreate(BaseModel):
    name: str
    description: str = ""
    variants: List[Dict]   # [{"name":"google","weight":50},...]
    metric: str = "bleu"


class AssignRequest(BaseModel):
    experiment: str
    unit_id: str


class ResultRequest(BaseModel):
    experiment: str
    unit_id: str
    metric_value: float
    metadata: Dict = {}


# ---------- مترجم عام ----------
TRANSLATOR = None
if CONFIG.get("translation", {}).get("enabled", False):
    try:
        from .translator import Translator

        TRANSLATOR = Translator(
            engine=CONFIG["translation"].get("engine", "google")
        )
        logger.info("المحرك الترجمي: %s", CONFIG["translation"]["engine"])
    except Exception as exc:
        logger.warning("تعذر تهيئة المحرك الترجمي: %s", exc)


# ---------- المقاييس ----------
from .metrics import PrometheusMiddleware, metrics_endpoint  # noqa: E402

# تفعيل Middleware
app.add_middleware(PrometheusMiddleware)


# ---------- Queue ----------
from .queue_worker import (  # noqa: E402
    enqueue_pdf, enqueue_epub, enqueue_ted, get_job_status,
)


# ============================================================
# Health + Metrics
# ============================================================
@app.get("/health")
async def health():
    """فحص صحة الخدمة."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "time": datetime.utcnow().isoformat(),
        "translation": bool(TRANSLATOR),
    }


# Endpoint المقاييس
@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_endpoint()


# ============================================================
# Auth Endpoints
# ============================================================
@app.post("/auth/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """تسجيل الدخول للحصول على JWT."""
    user = verify_user(form.username, form.password)
    if not user:
        raise HTTPException(401, "بيانات الدخول غير صحيحة")
    token = create_access_token({"sub": user.username, "role": user.role})
    return Token(
        access_token=token,
        expires_in=60 * 24 * 60,
    )


@app.get("/auth/me")
async def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


# ============================================================
# OCR المتزامن
# ============================================================
def _save_upload(file: UploadFile, subdir: str) -> Path:
    upload_dir = Path(CONFIG["storage"]["download_dir"]) / subdir
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{file.filename}"
    with open(save_path, "wb") as f:
        f.write(file.file.read())
    return save_path


@app.post("/ocr/pdf")
async def ocr_pdf(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),   # ← حماية
):
    """معالجة PDF متزامنة (ملفات صغيرة فقط)."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "الملف يجب أن يكون PDF")
    from .pdf_ocr import PDFOCRProcessor

    save_path = _save_upload(file, "api_pdf")
    result = PDFOCRProcessor(
        rules_file=CONFIG["ocr"]["rules_file"],
        output_dir=Path(CONFIG["storage"]["download_dir"]) / "api_pdf",
    ).process_and_save(save_path)
    return {
        "markdown": result["markdown"],
        "metadata": result["metadata"],
        "paths": result.get("paths", {}),
    }


@app.post("/ocr/epub")
async def ocr_epub(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """معالجة EPUB متزامنة."""
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(400, "الملف يجب أن يكون EPUB")
    from .epub_ocr import EpubOCRProcessor

    save_path = _save_upload(file, "api_epub")
    result = EpubOCRProcessor(
        rules_file=CONFIG["ocr"]["rules_file"],
        output_dir=Path(CONFIG["storage"]["download_dir"]) / "api_epub",
    ).process_and_save(save_path)
    return {
        "markdown": result["markdown"],
        "metadata": result["metadata"],
        "paths": result.get("paths", {}),
    }


# ============================================================
# OCR + TED غير المتزامن
# ============================================================
@app.post("/async/ocr/pdf")
async def async_ocr_pdf(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """استقبال PDF وإرجاع job_id فورًا."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "الملف يجب أن يكون PDF")

    # حفظ مؤقت دائم (Worker سيقرأه)
    save_path = _save_upload(file, "uploads")

    job_id = enqueue_pdf(
        str(save_path),
        str(Path(CONFIG["storage"]["download_dir"]) / "api_pdf"),
        CONFIG["ocr"]["rules_file"],
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/async/ocr/epub")
async def async_ocr_epub(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(400, "الملف يجب أن يكون EPUB")

    save_path = _save_upload(file, "uploads")

    job_id = enqueue_epub(
        str(save_path),
        str(Path(CONFIG["storage"]["download_dir"]) / "api_epub"),
        CONFIG["ocr"]["rules_file"],
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/async/ted/fetch")
async def async_ted_fetch(
    req: TedRequest,
    user: User = Depends(get_current_user),
):
    job_id = enqueue_ted(req.url, req.translate, req.target_lang)
    return {"job_id": job_id, "status": "queued"}


@app.get("/async/jobs/{job_id}")
async def job_status(
    job_id: str,
    user: User = Depends(get_current_user),
):
    """الاستعلام عن حالة job."""
    return get_job_status(job_id)


@app.get("/async/queue/stats")
async def queue_stats(user: User = Depends(get_current_user)):
    """إحصائيات الـ queue."""
    from .queue_worker import task_queue
    return {
        "queued": len(task_queue),
        "started": len(task_queue.started_job_registry),
        "finished": len(task_queue.finished_job_registry),
        "failed": len(task_queue.failed_job_registry),
        "deferred": len(task_queue.deferred_job_registry),
    }


# ============================================================
# TED + الترجمة المتزامنة
# ============================================================
@app.post("/ted/fetch")
async def ted_fetch(
    req: TedRequest,
    user: User = Depends(get_current_user),
):
    """جلب محادثة TED (متزامن — للمحادثات القصيرة)."""
    from .ted_fetcher import TedFetcher

    fetcher = TedFetcher(CONFIG)
    transcript = fetcher.fetch(req.url, target_lang=req.target_lang)
    if not transcript:
        raise HTTPException(502, "فشل جلب المحادثة")
    result = {
        "talk_id": transcript.talk_id,
        "title": transcript.title,
        "url": transcript.url,
        "source_text": transcript.source_text,
        "target_text": transcript.target_text,
    }
    if req.translate:
        if not TRANSLATOR:
            raise HTTPException(503, "الترجمة غير مفعّلة")
        auto = TRANSLATOR.translate(
            transcript.source_text, src="en", tgt=req.target_lang
        )
        result["auto_translation"] = auto.translated_text
    return result


@app.post("/translate")
async def translate(
    req: TranslateRequest,
    user: User = Depends(get_current_user),
):
    """ترجمة نص عبر المحرك المُهيأ."""
    if not TRANSLATOR:
        raise HTTPException(503, "الترجمة غير مفعّلة")
    result = TRANSLATOR.translate(req.text, src=req.src, tgt=req.tgt)
    return {
        "translated_text": result.translated_text,
        "engine": result.engine,
        "src": result.src,
        "tgt": result.tgt,
    }


# ============================================================
# اللغات (11 لغة RTL/LTR — منها en كلغة مصدر source_only)
# ============================================================
from .languages import get_registry  # noqa: E402


@app.get("/languages")
async def list_languages(user: User = Depends(get_current_user)):
    """قائمة اللغات المتاحة."""
    reg = get_registry()
    return {
        "languages": [
            {
                "code": code,
                "name": info["name"],
                "name_en": info["name_en"],
                "rtl": info["rtl"],
                "engines": list(info.get("models", {}).keys()),
            }
            for code, info in reg.data.items()
        ]
    }


class MultiTranslateRequest(BaseModel):
    text: str
    src: str = "auto"
    targets: List[str] = ["ar"]   # عدة لغات في طلب واحد


@app.post("/translate/multi")
async def translate_multi(
    req: MultiTranslateRequest,
    user: User = Depends(get_current_user),
):
    """ترجمة نص إلى عدة لغات في وقت واحد."""
    if not TRANSLATOR:
        raise HTTPException(503, "الترجمة غير مفعّلة")

    from .translator import MultiLangTranslator
    multi = MultiLangTranslator(engine=CONFIG["translation"]["engine"])

    results = {}
    for tgt in req.targets:
        try:
            r = multi.translate(req.text, src=req.src, tgt=tgt)
            results[tgt] = {
                "translation": r.translated_text,
                "rtl": get_registry().is_rtl(tgt),
            }
        except Exception as e:
            results[tgt] = {"error": str(e)}

    return {"source": req.text, "translations": results}


# ============================================================
# قواعد OCR + السجلات
# ============================================================
@app.get("/rules")
async def get_rules(user: User = Depends(get_current_user)):
    """عرض قواعد OCR الـ 18."""
    with open(CONFIG["ocr"]["rules_file"], encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    return rules


@app.get("/logs/recent")
async def recent_logs(
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    """آخر السجلات من مجلد البيانات."""
    logs_dir = Path(CONFIG["storage"].get("log_dir", "data/logs"))
    logs_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)[-5:]
    lines: List[str] = []
    for fp in files:
        lines.extend(
            fp.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        )
    return {"logs": lines[-limit:]}


# ============================================================
# الإدارة
# ============================================================
@app.get("/admin/stats")
async def admin_stats(user: User = Depends(require_admin)):
    return {"msg": f"مرحبًا أيها المدير {user.username}"}


# ============================================================
# Webhooks
# ============================================================
from .webhooks import (  # noqa: E402
    register_webhook, list_webhooks, delete_webhook, webhook_stats,
)


@app.post("/webhooks")
async def create_webhook(
    req: WebhookCreate,
    user: User = Depends(require_admin),
):
    """تسجيل webhook جديد (للمدير فقط)."""
    wh_id = register_webhook(req.url, req.secret, req.events)
    return {"id": wh_id, "status": "created"}


@app.get("/webhooks")
async def get_webhooks(user: User = Depends(get_current_user)):
    return list_webhooks()


@app.delete("/webhooks/{webhook_id}")
async def remove_webhook(
    webhook_id: int,
    user: User = Depends(require_admin),
):
    ok = delete_webhook(webhook_id)
    if not ok:
        raise HTTPException(404, "Webhook غير موجود")
    return {"status": "deleted"}


@app.get("/webhooks/stats")
async def get_webhook_stats(user: User = Depends(get_current_user)):
    return webhook_stats()


@app.post("/webhooks/test/{webhook_id}")
async def test_webhook(
    webhook_id: int,
    user: User = Depends(require_admin),
):
    """إرسال حدث تجريبي."""
    import sqlite3

    from .webhooks import deliver, get_webhooks_for_event
    webhooks = [w for w in list_webhooks() if w["id"] == webhook_id]
    if not webhooks:
        raise HTTPException(404, "Webhook غير موجود")

    # الحصول على السر من قاعدة البيانات
    from .webhooks import WEBHOOK_DB

    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        row = conn.execute(
            "SELECT id, url, secret, events FROM webhooks WHERE id = ?",
            (webhook_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Webhook غير موجود")

    webhook = {"id": row[0], "url": row[1], "secret": row[2], "events": row[3]}
    ok = deliver(webhook, "test", {"ping": True, "by": user.username})
    return {"delivered": ok}


# ============================================================
# CMS
# ============================================================
from .cms import create_adapter  # noqa: E402


@app.post("/cms/publish")
async def cms_publish(
    req: PublishRequest,
    user: User = Depends(get_current_user),
):
    """نشر محتوى إلى CMS."""
    adapters = CONFIG.get("cms", {}).get("adapters", [])
    cfg = next((a for a in adapters if a["type"] == req.cms_type), None)
    if not cfg:
        raise HTTPException(404, f"CMS غير مهيأ: {req.cms_type}")

    kwargs = {k: v for k, v in cfg.items() if k != "type"}
    adapter = create_adapter(req.cms_type, **kwargs)
    result = adapter.publish(req.title, req.content, req.tags)
    if not result.success:
        raise HTTPException(500, result.error)
    return {"url": result.url, "post_id": result.post_id}


# ============================================================
# الجودة
# ============================================================
from .quality.metrics import QualityEvaluator  # noqa: E402
from .quality.auto_quality import get_recent_runs, detect_degradation  # noqa: E402

_evaluator = QualityEvaluator(use_comet=True, use_bertscore=True)


@app.post("/quality/evaluate")
async def evaluate_quality(
    req: QualityRequest,
    user: User = Depends(get_current_user),
):
    """تقييم جودة ترجمات."""
    if len(req.predictions) != len(req.references):
        raise HTTPException(400, "عدد predictions يجب أن يساوي references")
    score = _evaluator.evaluate(
        req.predictions, req.references, req.sources,
    )
    return _evaluator.to_dict(score)


@app.get("/quality/history")
async def quality_history(
    limit: int = 30,
    user: User = Depends(get_current_user),
):
    return {"runs": get_recent_runs(limit)}


@app.get("/quality/alerts")
async def quality_alerts(user: User = Depends(get_current_user)):
    alert = detect_degradation()
    return {"alert": alert, "status": "degraded" if alert else "ok"}


# ============================================================
# A/B Testing
# ============================================================
from .ab_testing import (  # noqa: E402
    create_experiment, list_experiments, get_experiment,
    assign_variant, record_result, analyze_experiment,
    auto_select_winner, pause_experiment, complete_experiment,
)


@app.post("/ab/experiments")
async def create_ab_experiment(
    req: ExperimentCreate,
    user: User = Depends(require_admin),
):
    try:
        eid = create_experiment(
            req.name, req.description, req.variants, req.metric
        )
        return {"id": eid, "status": "created"}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/ab/experiments")
async def list_ab_experiments(user: User = Depends(get_current_user)):
    return list_experiments()


@app.get("/ab/experiments/{name}")
async def get_ab_experiment(
    name: str,
    user: User = Depends(get_current_user),
):
    exp = get_experiment(name)
    if not exp:
        raise HTTPException(404, "التجربة غير موجودة")
    return exp


@app.post("/ab/assign")
async def assign_ab(
    req: AssignRequest,
    user: User = Depends(get_current_user),
):
    variant = assign_variant(req.experiment, req.unit_id)
    if not variant:
        raise HTTPException(404, "لا توجد تجربة نشطة بهذا الاسم")
    return {"unit_id": req.unit_id, "variant": variant}


@app.post("/ab/results")
async def record_ab_result(
    req: ResultRequest,
    user: User = Depends(get_current_user),
):
    """تسجيل نتيجة قياس لوحدة مخصصة."""
    try:
        record_result(
            req.experiment, req.unit_id, req.metric_value, req.metadata
        )
        return {"status": "recorded"}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/ab/experiments/{name}/analyze")
async def analyze_ab(
    name: str,
    user: User = Depends(get_current_user),
):
    """تحليل إحصائي (t-test) للتجربة."""
    try:
        return analyze_experiment(name)
    except Exception as e:
        raise HTTPException(404, str(e))


@app.get("/ab/experiments/{name}/winner")
async def ab_winner(
    name: str,
    min_samples: int = 100,
    user: User = Depends(get_current_user),
):
    """الفائز التلقائي عند الأهلية الإحصائية."""
    try:
        return auto_select_winner(name, min_samples=min_samples)
    except Exception as e:
        raise HTTPException(404, str(e))


@app.post("/ab/experiments/{name}/pause")
async def pause_ab(
    name: str,
    user: User = Depends(require_admin),
):
    ok = pause_experiment(name)
    if not ok:
        raise HTTPException(404, "التجربة غير موجودة")
    return {"status": "paused"}


# ============================================================
# ASR — تحويل الصوت إلى نص وترجمة
# ============================================================
from .asr.pipeline import (  # noqa: E402
    transcribe_and_translate, extract_audio_from_video,
)
from .asr import create_engine  # noqa: E402
import shutil  # noqa: E402


@app.post("/asr/transcribe")
async def asr_transcribe(
    file: UploadFile = File(...),
    source_lang: str = "en",
    target_lang: str = "ar",
    asr_engine: str = "whisper-local",
    translator_engine: str = "google",
    user: User = Depends(get_current_user),
):
    """نسخ صوتي كامل + ترجمة."""
    upload_dir = Path(CONFIG["storage"]["download_dir"]) / "asr_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / file.filename

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # إذا كان فيديو، استخرج الصوت
    if save_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
        audio_path = extract_audio_from_video(str(save_path))
    else:
        audio_path = str(save_path)

    result = transcribe_and_translate(
        audio_path=audio_path,
        source_lang=source_lang,
        target_lang=target_lang,
        asr_engine=asr_engine,
        translator_engine=translator_engine,
    )
    return result


@app.post("/asr/async/transcribe")
async def asr_transcribe_async(
    file: UploadFile = File(...),
    source_lang: str = "en",
    target_lang: str = "ar",
    user: User = Depends(get_current_user),
):
    """نسخ صوتي غير متزامن (للملفات الطويلة)."""
    upload_dir = Path(CONFIG["storage"]["download_dir"]) / "asr_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    from .queue_worker import task_queue
    job = task_queue.enqueue(
        "src.asr.tasks.asr_task",
        str(save_path), source_lang, target_lang,
        job_timeout="2h",
        result_ttl=86400,
    )
    return {"job_id": job.id, "status": "queued"}
