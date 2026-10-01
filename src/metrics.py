"""
مقاييس Prometheus لمشروع الماراثون.
تُصدَّر على endpoint /metrics في API.
"""
import time
import logging
from functools import wraps
from typing import Callable

from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    generate_latest, CONTENT_TYPE_LATEST,
)
from fastapi import Response

logger = logging.getLogger(__name__)

# ---------- تعريف المقاييس ----------
APP_INFO = Info("marathon_app", "معلومات التطبيق")
APP_INFO.info({
    "version": "1.0.0",
    "service": "marathon",
})

# عداد الطلبات
HTTP_REQUESTS = Counter(
    "marathon_http_requests_total",
    "إجمالي طلبات HTTP",
    ["method", "endpoint", "status"],
)

# مدة الطلبات
HTTP_DURATION = Histogram(
    "marathon_http_duration_seconds",
    "مدة طلبات HTTP بالثواني",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

# معالجة الملفات
FILES_PROCESSED = Counter(
    "marathon_files_processed_total",
    "عدد الملفات المعالجة",
    ["type", "status"],     # type: pdf|epub, status: success|failed
)

# مدة معالجة الملفات
FILE_PROCESS_DURATION = Histogram(
    "marathon_file_process_duration_seconds",
    "مدة معالجة الملفات",
    ["type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

# الترجمات
TRANSLATIONS = Counter(
    "marathon_translations_total",
    "عدد الترجمات المنفذة",
    ["engine", "status"],
)

# Queue
QUEUE_SIZE = Gauge(
    "marathon_queue_size",
    "حجم الـ queue الحالي",
    ["queue_name"],
)
QUEUE_JOBS = Gauge(
    "marathon_queue_jobs",
    "عدد الـ jobs في كل حالة",
    ["state"],     # queued|started|finished|failed|deferred
)

# تيليجرام
TELEGRAM_UPLOADS = Counter(
    "marathon_telegram_uploads_total",
    "عدد الملفات المرفوعة إلى تيليجرام",
    ["status"],
)

# الرموز البصرية المكتشفة
VISUAL_MARKERS = Counter(
    "marathon_visual_markers_total",
    "عدد الرموز البصرية المكتشفة",
    ["kind"],     # check|x|other
)

# عدم اليقين
UNCERTAIN_FLAGS = Counter(
    "marathon_uncertain_flags_total",
    "عدد الحالات المُعلَّمة كغير مؤكدة",
    ["label"],
)


# ---------- Middleware للـ FastAPI ----------
class PrometheusMiddleware:
    """Middleware لتسجيل كل طلب HTTP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]

        # تجاهل /metrics نفسه
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        start = time.time()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start
            # تبسيط المسارات الديناميكية
            endpoint = path
            for prefix in ("/async/jobs/", "/admin/"):
                if path.startswith(prefix):
                    endpoint = prefix.rstrip("/") + "/{id}"
                    break

            HTTP_REQUESTS.labels(method, endpoint, status_code).inc()
            HTTP_DURATION.labels(method, endpoint).observe(duration)


# ---------- Helper لتزيين الدوال ----------
def track_file_processing(file_type: str):
    """Decorator لتتبع معالجة الملفات."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                status = "failed"
                raise
            finally:
                duration = time.time() - start
                FILES_PROCESSED.labels(file_type, status).inc()
                FILE_PROCESS_DURATION.labels(file_type).observe(duration)
        return wrapper
    return decorator


# ---------- تحديث مقاييس Queue ----------
def update_queue_metrics():
    """يُستدعى دوريًا لتحديث مقاييس Queue من Redis."""
    try:
        from .queue_worker import task_queue
        QUEUE_SIZE.labels("marathon_tasks").set(len(task_queue))
        QUEUE_JOBS.labels("queued").set(len(task_queue))
        QUEUE_JOBS.labels("started").set(len(task_queue.started_job_registry))
        QUEUE_JOBS.labels("finished").set(len(task_queue.finished_job_registry))
        QUEUE_JOBS.labels("failed").set(len(task_queue.failed_job_registry))
        QUEUE_JOBS.labels("deferred").set(len(task_queue.deferred_job_registry))
    except Exception as e:
        logger.warning("فشل تحديث مقاييس queue: %s", e)


# ---------- Endpoint ----------
def metrics_endpoint() -> Response:
    update_queue_metrics()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
