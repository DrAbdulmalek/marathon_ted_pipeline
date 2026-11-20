"""Persistent, idempotent state for Telegram source-channel ingestion."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class TelegramIngestionState:
    """SQLite-backed message ledger.

    A source message is uniquely identified by (source_id, message_id).
    Claims prevent concurrent duplicate processing; stale claims can be retried.
    """

    def __init__(self, path: str = "data/telegram_ingestion.sqlite3", claim_ttl: int = 3600):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.claim_ttl = claim_ttl
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS telegram_messages (
                    source_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing','done')),
                    claimed_at REAL NOT NULL,
                    completed_at REAL,
                    PRIMARY KEY (source_id, message_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS telegram_cursors (
                    source_id TEXT PRIMARY KEY,
                    last_scanned_message_id INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
            """)

    def claim(self, source_id: str, message_id: int) -> bool:
        now = time.time()
        with self._connect() as db:
            row = db.execute(
                "SELECT status, claimed_at FROM telegram_messages "
                "WHERE source_id=? AND message_id=?",
                (str(source_id), int(message_id)),
            ).fetchone()
            if row and row[0] == "done":
                return False
            if row and now - row[1] < self.claim_ttl:
                return False
            db.execute(
                "INSERT INTO telegram_messages "
                "(source_id,message_id,status,claimed_at) VALUES (?,?,?,?) "
                "ON CONFLICT(source_id,message_id) DO UPDATE SET "
                "status='processing', claimed_at=excluded.claimed_at, completed_at=NULL",
                (str(source_id), int(message_id), "processing", now),
            )
            return True

    def mark_done(self, source_id: str, message_id: int) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE telegram_messages SET status='done', completed_at=? "
                "WHERE source_id=? AND message_id=?",
                (time.time(), str(source_id), int(message_id)),
            )

    def release(self, source_id: str, message_id: int) -> None:
        """Allow a failed message to be retried immediately."""
        with self._connect() as db:
            db.execute(
                "DELETE FROM telegram_messages WHERE source_id=? AND message_id=? "
                "AND status='processing'",
                (str(source_id), int(message_id)),
            )

    def is_done(self, source_id: str, message_id: int) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT status FROM telegram_messages WHERE source_id=? AND message_id=?",
                (str(source_id), int(message_id)),
            ).fetchone()
            return bool(row and row[0] == "done")

    def get_cursor(self, source_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT last_scanned_message_id FROM telegram_cursors WHERE source_id=?",
                (str(source_id),),
            ).fetchone()
            return int(row[0]) if row else 0

    def set_cursor(self, source_id: str, message_id: int) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO telegram_cursors(source_id,last_scanned_message_id,updated_at) "
                "VALUES(?,?,?) ON CONFLICT(source_id) DO UPDATE SET "
                "last_scanned_message_id=excluded.last_scanned_message_id, "
                "updated_at=excluded.updated_at",
                (str(source_id), int(message_id), time.time()),
            )

    def count_done(self, source_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM telegram_messages WHERE source_id=? AND status='done'",
                (str(source_id),),
            ).fetchone()
            return int(row[0])
