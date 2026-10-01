import os
import pytest
from pathlib import Path

# قاعدة بيانات اختبار معزولة
os.environ["AUTH_DB"] = "data/test_auth.db"

from src.auth import (
    init_db, create_user, verify_user, create_api_key,
    verify_api_key, create_access_token, decode_token,
)


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    os.environ["AUTH_DB"] = str(tmp_path / "test.db")
    # إعادة تحميل الوحدة لتحديث DB_PATH
    import importlib
    import src.auth
    importlib.reload(src.auth)
    src.auth.init_db()
    yield
    Path(os.environ["AUTH_DB"]).unlink(missing_ok=True)


def test_create_and_verify_user():
    import src.auth as auth
    auth.create_user("alice", "s3cret", "user")
    user = auth.verify_user("alice", "s3cret")
    assert user is not None
    assert user.username == "alice"
    assert user.role == "user"


def test_wrong_password_rejected():
    import src.auth as auth
    auth.create_user("bob", "pass1")
    assert auth.verify_user("bob", "wrong") is None


def test_api_key_roundtrip():
    import src.auth as auth
    key = auth.create_api_key("script1", "admin")
    assert key.startswith("mrt_")
    user = auth.verify_api_key(key)
    assert user is not None
    assert user.role == "admin"


def test_invalid_api_key():
    import src.auth as auth
    assert auth.verify_api_key("invalid") is None
    assert auth.verify_api_key("") is None


def test_jwt_roundtrip():
    import src.auth as auth
    token = auth.create_access_token({"sub": "alice", "role": "user"})
    data = auth.decode_token(token)
    assert data.username == "alice"
    assert data.role == "user"


def test_jwt_invalid_raises():
    import src.auth as auth
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        auth.decode_token("garbage.token.here")


# ---------- Queue Tests ----------
@pytest.mark.asyncio
async def test_enqueue_and_get_status():
    """يحتاج Redis. يعمل فقط إذا كان متاحًا."""
    try:
        from redis import Redis
        r = Redis.from_url("redis://localhost:6379/0")
        r.ping()
    except Exception:
        pytest.skip("Redis غير متاح")

    from src.queue_worker import enqueue_ted, get_job_status
    job_id = enqueue_ted("https://www.ted.com/talks/test", translate=False)
    assert job_id
    status = get_job_status(job_id)
    assert status["job_id"] == job_id
    assert status["status"] in (
        "queued", "started", "finished", "failed", "deferred"
    )
