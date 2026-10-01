# src/queue_worker.py
"""
معالجة غير متزامنة عبر Redis Queue:
- API يستقبل الملفات ويرجع job_id فورًا
- Worker يعالج الملفات في الخلفية
- API يوفر endpoint للاستعلام عن حالة الـ job
- عند اكتمال/فشل كل مهمة يُطلق حدث webhook (job.completed / job.failed)
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from redis import Redis
from rq import Queue, Worker, Connection
from rq.job import Job

from .pdf_ocr import PDFOCRProcessor
from .epub_ocr import EpubOCRProcessor

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = "marathon_tasks"

redis_conn = Redis.from_url(REDIS_URL)
task_queue = Queue(QUEUE_NAME, connection=redis_conn)


def _fire(event: str, payload: dict) -> None:
    """إطلاق حدث webhook بأمان — لا يعطل المهمة أبدًا."""
    try:
        from .webhooks import fire_event
        fire_event(event, payload)
    except Exception as exc:  # webhooks اختيارية
        logger.debug("fire_event تجاهل: %s", exc)


# ---------- المهام (تُنفَّذ في Worker) ----------
def process_pdf_task(pdf_path: str, output_dir: str, rules_file: str) -> dict:
    """معالجة PDF في الخلفية."""
    logger.info("بدء معالجة PDF: %s", pdf_path)
    try:
        proc = PDFOCRProcessor(rules_file=rules_file, output_dir=Path(output_dir))
        result = proc.process(Path(pdf_path))

        out_dir = Path(output_dir) / Path(pdf_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{Path(pdf_path).stem}.md"
        meta_path = out_dir / f"{Path(pdf_path).stem}.meta.json"

        md_path.write_text(result["markdown"], encoding="utf-8")
        meta_path.write_text(
            json.dumps(result["metadata"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = {
            "markdown_path": str(md_path),
            "metadata_path": str(meta_path),
            "metadata": result["metadata"],
        }
        _fire("job.completed", {
            "type": "pdf",
            "file": pdf_path,
            "markdown_path": str(md_path),
            "metadata": result["metadata"],
        })
        return result
    except Exception as e:
        _fire("job.failed", {"type": "pdf", "file": pdf_path, "error": str(e)})
        raise


def process_epub_task(epub_path: str, output_dir: str, rules_file: str) -> dict:
    """معالجة EPUB في الخلفية."""
    logger.info("بدء معالجة EPUB: %s", epub_path)
    try:
        proc = EpubOCRProcessor(rules_file=rules_file, output_dir=Path(output_dir))
        result = proc.process(Path(epub_path))

        out_dir = Path(output_dir) / Path(epub_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{Path(epub_path).stem}.md"
        meta_path = out_dir / f"{Path(epub_path).stem}.meta.json"

        md_path.write_text(result["markdown"], encoding="utf-8")
        meta_path.write_text(
            json.dumps(result["metadata"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = {
            "markdown_path": str(md_path),
            "metadata_path": str(meta_path),
            "metadata": result["metadata"],
        }
        _fire("job.completed", {
            "type": "epub",
            "file": epub_path,
            "markdown_path": str(md_path),
            "metadata": result["metadata"],
        })
        return result
    except Exception as e:
        _fire("job.failed", {"type": "epub", "file": epub_path, "error": str(e)})
        raise


def ted_fetch_task(ted_url: str, translate: bool = False,
                    target_lang: str = "ar") -> dict:
    """جلب ترجمة TED في الخلفية."""
    try:
        from .ted_fetcher import TedFetcher
        import yaml
        with open("config/config.yaml", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        fetcher = TedFetcher(config)
        transcript = fetcher.fetch(ted_url)
        if not transcript:
            raise RuntimeError("فشل جلب المحادثة")

        result = {
            "talk_id": transcript.talk_id,
            "title": transcript.title,
            "url": transcript.url,
            "source_text": transcript.source_text,
            "target_text": transcript.target_text,
        }

        if translate:
            from .translator import Translator
            t = Translator(engine="google")
            auto = t.translate(
                transcript.source_text,
                src=transcript.source_lang,
                tgt=target_lang,
            )
            result["auto_translation"] = auto.translated_text

        _fire("job.completed", {"type": "ted", "url": ted_url, "title": transcript.title})
        return result
    except Exception as e:
        _fire("job.failed", {"type": "ted", "url": ted_url, "error": str(e)})
        raise


# ---------- دوال إدارة الـ jobs ----------
def enqueue_pdf(pdf_path: str, output_dir: str, rules_file: str) -> str:
    job = task_queue.enqueue(
        process_pdf_task,
        pdf_path, output_dir, rules_file,
        job_timeout="30m",
        result_ttl=86400,  # يوم
    )
    return job.id


def enqueue_epub(epub_path: str, output_dir: str, rules_file: str) -> str:
    job = task_queue.enqueue(
        process_epub_task,
        epub_path, output_dir, rules_file,
        job_timeout="30m",
        result_ttl=86400,
    )
    return job.id


def enqueue_ted(ted_url: str, translate: bool = False,
                 target_lang: str = "ar") -> str:
    job = task_queue.enqueue(
        ted_fetch_task,
        ted_url, translate, target_lang,
        job_timeout="15m",
        result_ttl=86400,
    )
    return job.id


def get_job_status(job_id: str) -> dict:
    """حالة الـ job."""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return {"status": "not_found", "job_id": job_id}

    return {
        "job_id": job.id,
        "status": job.get_status(),
        "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        "result": job.result if job.is_finished else None,
        "error": str(job.exc_info) if job.is_failed else None,
    }


# ---------- Worker CLI ----------
def run_worker():
    """تشغيل worker للاستماع للـ queue."""
    with Connection(redis_conn):
        worker = Worker([task_queue])
        logger.info("Worker بدأ العمل على queue: %s", QUEUE_NAME)
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
