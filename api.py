# api.py — نقطة دخول REST API (uvicorn src.api:app)
"""
تشغيل: uvicorn src.api:app --host 0.0.0.0 --port 8000
هذا الملف موجود للتوافق مع systemctl scripts وdocker compose.
"""
from src.api import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="0.0.0.0", port=8000)
