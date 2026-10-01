"""
نظام Webhooks:
- تسجيل endpoints خارجية لاستقبال أحداث
- إشعارات عند اكتمال/فشل jobs
- توقيع HMAC-SHA256 لكل طلب
- إعادة محاولة مع backoff
"""
import os
import hmac
import json
import time
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_DB = Path(os.getenv("WEBHOOK_DB", "data/webhooks.db"))
WEBHOOK_DB.parent.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 5
RETRY_BACKOFF = [5, 15, 60, 300, 1800]  # ثواني


# ---------- قاعدة البيانات ----------
def init_db():
    conn = sqlite3.connect(WEBHOOK_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            secret TEXT NOT NULL,
            events TEXT NOT NULL,          -- JSON array
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            payload TEXT NOT NULL,
            status_code INTEGER,
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            delivered_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(webhook_id) REFERENCES webhooks(id)
        );
    """)
    conn.commit()
    conn.close()


# ---------- إدارة ----------
def register_webhook(url: str, secret: str, events: List[str]) -> int:
    """تسجيل webhook جديد."""
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        cur = conn.execute(
            "INSERT INTO webhooks (url, secret, events) VALUES (?, ?, ?)",
            (url, secret, json.dumps(events)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_webhooks() -> List[Dict]:
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        rows = conn.execute(
            "SELECT id, url, events, active, created_at FROM webhooks"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "url": r[1], "events": json.loads(r[2]),
         "active": bool(r[3]), "created_at": r[4]}
        for r in rows
    ]


def delete_webhook(webhook_id: int) -> bool:
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        cur = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_webhooks_for_event(event: str) -> List[Dict]:
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        rows = conn.execute(
            "SELECT id, url, secret, events FROM webhooks WHERE active = 1"
        ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        events = json.loads(r[3])
        if event in events or "*" in events:
            result.append({"id": r[0], "url": r[1], "secret": r[2]})
    return result


# ---------- الإرسال ----------
def _sign_payload(payload: bytes, secret: str) -> str:
    """توقيع HMAC-SHA256."""
    return hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()


def _record_delivery(webhook_id: int, event: str, payload: dict,
                      status_code: Optional[int], attempts: int,
                      last_error: Optional[str] = None):
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        conn.execute(
            """INSERT INTO deliveries
               (webhook_id, event, payload, status_code, attempts,
                last_error, delivered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (webhook_id, event, json.dumps(payload, ensure_ascii=False),
             status_code, attempts, last_error,
             datetime.now(timezone.utc).isoformat() if status_code == 200 else None),
        )
        conn.commit()
    finally:
        conn.close()


def deliver(webhook: Dict, event: str, payload: dict, attempt: int = 1) -> bool:
    """إرسال webhook واحد مع توقيع."""
    body = json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }, ensure_ascii=False).encode("utf-8")

    signature = _sign_payload(body, webhook["secret"])
    headers = {
        "Content-Type": "application/json",
        "X-Marathon-Event": event,
        "X-Marathon-Signature": f"sha256={signature}",
        "X-Marathon-Delivery": str(attempt),
        "User-Agent": "Marathon-Webhook/1.0",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(webhook["url"], content=body, headers=headers)

        if 200 <= resp.status_code < 300:
            logger.info("✅ webhook %d نجح (%d)", webhook["id"], resp.status_code)
            _record_delivery(webhook["id"], event, payload,
                             resp.status_code, attempt)
            return True
        else:
            logger.warning("⚠️ webhook %d فشل: %d", webhook["id"], resp.status_code)
            _record_delivery(webhook["id"], event, payload,
                             resp.status_code, attempt,
                             last_error=f"HTTP {resp.status_code}")
            return False

    except Exception as e:
        logger.warning("❌ webhook %d خطأ: %s", webhook["id"], e)
        _record_delivery(webhook["id"], event, payload,
                         None, attempt, last_error=str(e))
        return False


# ---------- الإرسال الرئيسي (يُستدعى من المهام) ----------
def fire_event(event: str, payload: dict):
    """
    إرسال حدث لكل الـ webhooks المسجلة.
    يُستدعى من مهام queue_worker عند الانتهاء/الفشل.
    """
    webhooks = get_webhooks_for_event(event)
    if not webhooks:
        return

    logger.info("🔥 إطلاق event '%s' لـ %d webhook",
                event, len(webhooks))

    for wh in webhooks:
        # محاولة أولى متزامنة
        ok = deliver(wh, event, payload, attempt=1)
        if not ok:
            # جدولة إعادة محاولة عبر RQ (في الخلفية)
            try:
                from .queue_worker import task_queue
                task_queue.enqueue(
                    retry_webhook_task,
                    wh, event, payload, 2,
                    job_timeout="1h",
                )
            except Exception as e:
                logger.exception("فشل جدولة إعادة محاولة: %s", e)


def retry_webhook_task(webhook: Dict, event: str, payload: dict, attempt: int):
    """مهمة إعادة محاولة في queue."""
    if attempt > MAX_RETRIES:
        logger.error("🚫 webhook %d فشل نهائيًا بعد %d محاولات",
                     webhook["id"], attempt - 1)
        return

    # انتظار حسب backoff
    wait = RETRY_BACKOFF[min(attempt - 2, len(RETRY_BACKOFF) - 1)]
    logger.info("⏳ إعادة محاولة webhook %d بعد %ds (محاولة %d)",
                webhook["id"], wait, attempt)
    time.sleep(wait)

    ok = deliver(webhook, event, payload, attempt=attempt)
    if not ok:
        from .queue_worker import task_queue
        task_queue.enqueue(
            retry_webhook_task,
            webhook, event, payload, attempt + 1,
            job_timeout="1h",
        )


# ---------- إحصائيات ----------
def webhook_stats() -> Dict:
    conn = sqlite3.connect(WEBHOOK_DB)
    try:
        total = conn.execute("SELECT COUNT(*) FROM webhooks").fetchone()[0]
        deliveries = conn.execute(
            "SELECT status_code, COUNT(*) FROM deliveries GROUP BY status_code"
        ).fetchall()
    finally:
        conn.close()
    return {
        "total_webhooks": total,
        "deliveries_by_status": {str(s): c for s, c in deliveries},
    }


init_db()
