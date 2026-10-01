"""
تقييم تلقائي مستمر:
- يُشغَّل على عينة عشوائية بعد كل دفعة
- يسجّل النتائج في SQLite
- ينبّه عند التدهور
"""
import os
import random
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .metrics import QualityEvaluator, QualityScore

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("QUALITY_DB", "data/quality.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quality_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            model TEXT,
            samples INTEGER NOT NULL,
            bleu REAL, chrf REAL, meteor REAL,
            comet REAL, bertscore REAL,
            overall REAL, level TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_quality_created
            ON quality_runs(created_at);
    """)
    conn.commit()
    conn.close()


def record_run(engine: str, model: Optional[str],
               samples: int, score: QualityScore):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO quality_runs
               (engine, model, samples, bleu, chrf, meteor,
                comet, bertscore, overall, level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (engine, model, samples,
             score.bleu, score.chrf, score.meteor,
             score.comet, score.bertscore,
             score.overall, score.level),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_runs(limit: int = 30) -> list:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT engine, model, samples, overall, level, created_at
               FROM quality_runs
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"engine": r[0], "model": r[1], "samples": r[2],
         "overall": r[3], "level": r[4], "created_at": r[5]}
        for r in rows
    ]


def detect_degradation(window: int = 5, threshold: float = 10.0) -> Optional[str]:
    """كشف تدهور الجودة > threshold نقطة."""
    runs = get_recent_runs(limit=window * 2)
    if len(runs) < window * 2:
        return None

    recent = [r["overall"] for r in runs[:window] if r["overall"] is not None]
    previous = [r["overall"] for r in runs[window:window * 2]
                if r["overall"] is not None]

    if not recent or not previous:
        return None

    avg_recent = sum(recent) / len(recent)
    avg_prev = sum(previous) / len(previous)

    if avg_prev - avg_recent > threshold:
        return (f"⚠️ تدهور جودة: {avg_prev:.1f} → {avg_recent:.1f} "
                f"(-{avg_prev - avg_recent:.1f})")
    return None


init_db()
