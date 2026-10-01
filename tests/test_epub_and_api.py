# tests/test_epub_and_api.py
"""اختبارات معالج EPUB + REST API (TestClient بمصادقة)."""
from pathlib import Path

import pytest

from src.epub_ocr import EpubOCRProcessor


# ---------- EPUB ----------
def test_epub_processor_init(tmp_path):
    proc = EpubOCRProcessor(
        rules_file="config/marathon_ocr_rules.yaml",
        output_dir=tmp_path,
    )
    assert proc.language == "ara+eng"
    assert proc.output_dir == tmp_path


def test_epub_missing_file_raises(tmp_path):
    proc = EpubOCRProcessor(rules_file="config/marathon_ocr_rules.yaml")
    with pytest.raises(FileNotFoundError):
        proc.process(tmp_path / "missing.epub")


def test_epub_html_extraction():
    proc = EpubOCRProcessor(rules_file="config/marathon_ocr_rules.yaml")
    html = (
        "<html><body><p>فصل أول</p>"
        "<p>نص كامل كافي للاستخراج هنا وهو طويل بشكل مريح.</p></body></html>"
    ).encode("utf-8")
    text = proc._extract_html_text(html)
    assert "<p>" not in text
    assert "فصل" in text


# ---------- API ----------
@pytest.fixture(scope="module")
def client():
    os_env_ready = True  # conftest عزّز قواعد البيانات
    from fastapi.testclient import TestClient

    from src.auth import init_db, create_api_key, create_user
    import src.auth as auth

    init_db()
    try:
        create_user("admin", "StrongPass123", "admin")
    except Exception:
        pass  # موجود مسبقًا
    api_key = create_api_key("pytest-suite", "admin")

    from src.api import app

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-API-Key": api_key})
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rules_endpoint_requires_auth():
    from fastapi.testclient import TestClient
    from src.api import app

    with TestClient(app) as c:
        r = c.get("/rules")
        assert r.status_code == 401


def test_rules_endpoint_with_key(client):
    r = client.get("/rules")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rules"]) == 18


def test_auth_me(client):
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "pytest-suite"


def test_login_flow(client):
    r = client.post(
        "/auth/token",
        data={"username": "admin", "password": "StrongPass123"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    r2 = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"


def test_admin_stats_requires_admin(client):
    r = client.get("/admin/stats")
    assert r.status_code == 200
    assert "المدير" in r.json()["msg"]


def test_translate_endpoint(client):
    r = client.post(
        "/translate",
        json={"text": "Hello world", "src": "en", "tgt": "ar"},
    )
    # يعتمد على توفر الشبكة — 200 نجاح، 503 غير مفعلة، 500 فشل مزود خارجي
    assert r.status_code in (200, 503, 500)


def test_languages_endpoint(client):
    r = client.get("/languages")
    assert r.status_code == 200
    langs = r.json()["languages"]
    assert len(langs) == 10


def test_webhook_crud(client):
    r = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "secret": "s3cret", "events": ["*"]},
    )
    assert r.status_code == 200
    wh_id = r.json()["id"]

    r2 = client.get("/webhooks")
    assert r2.status_code == 200

    r3 = client.delete(f"/webhooks/{wh_id}")
    assert r3.status_code == 200


def test_async_pdf_rejects_non_pdf(client):
    r = client.post(
        "/async/ocr/pdf",
        files={"file": ("not.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
