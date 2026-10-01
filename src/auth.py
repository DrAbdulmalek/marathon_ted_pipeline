"""
نظام مصادقة مزدوج:
- API Key للاستدعاءات البسيطة (سكربتات، webhooks)
- JWT للواجهات التفاعلية (dashboard, SPA)
- تخزين العملاء في SQLite محلي
"""
import os
import json
import hashlib
import secrets
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------- الإعدادات ----------
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(64))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 ساعة
DB_PATH = Path(os.getenv("AUTH_DB", "data/auth.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


# ---------- نماذج ----------
class User(BaseModel):
    username: str
    role: str = "user"     # user | admin


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


# ---------- قاعدة البيانات ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_used TEXT,
            active INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ---------- إدارة المستخدمين ----------
def create_user(username: str, password: str, role: str = "user"):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pwd_context.hash(password), role),
        )
        conn.commit()
    finally:
        conn.close()


def verify_user(username: str, password: str) -> Optional[User]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[3]:
        return None
    if not pwd_context.verify(password, row[1]):
        return None
    return User(username=row[0], role=row[2])


# ---------- إدارة API Keys ----------
def create_api_key(name: str, role: str = "user") -> str:
    """يولّد مفتاحًا جديدًا ويخزن hash فقط."""
    key = f"mrt_{secrets.token_urlsafe(32)}"
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO api_keys (key_hash, name, role) VALUES (?, ?, ?)",
            (hash_api_key(key), name, role),
        )
        conn.commit()
    finally:
        conn.close()
    return key


def verify_api_key(key: str) -> Optional[User]:
    if not key:
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT name, role, active FROM api_keys WHERE key_hash = ?",
            (hash_api_key(key),),
        ).fetchone()
        if row and row[2]:
            conn.execute(
                "UPDATE api_keys SET last_used = ? WHERE key_hash = ?",
                (datetime.now(timezone.utc).isoformat(), hash_api_key(key)),
            )
            conn.commit()
    finally:
        conn.close()
    if not row:
        return None
    return User(username=row[0], role=row[1])


# ---------- JWT ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(
            username=payload.get("sub"),
            role=payload.get("role"),
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="توكن غير صالح",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------- Dependencies ----------
async def get_current_user(
    api_key: Optional[str] = Security(api_key_header),
    token: Optional[str] = Security(oauth2_scheme),
) -> User:
    """يقبل API Key أو JWT."""
    if api_key:
        user = verify_api_key(api_key)
        if user:
            return user

    if token:
        data = decode_token(token)
        if data.username:
            return User(username=data.username, role=data.role or "user")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="مصادقة مطلوبة (X-API-Key أو Bearer Token)",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "صلاحيات المدير مطلوبة")
    return user
