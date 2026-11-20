import os
import json
import hmac
import hashlib
import tempfile
from pathlib import Path

import pytest

# كان هذا السطر `os.environ["WEBHOOK_DB"] = "data/test_webhooks.db"` — أي مسار
# **داخل المستودع ومتتبَّع في git**. ونتيجته أن `import src.webhooks` في السطر
# التالي كان يكتب في ذلك الملف عند كل تشغيل اختبار، فيلوّث شجرة العمل
# (git status يظهر `M data/test_webhooks.db`) ويبني artifact ثنائياً في git.
#
# الإصلاح: setdefault (حتى يبقى عزل conftest.py هو الفائز) + مسار في مجلد
# مؤقت خارج المستودع. السلوك الاختباري لا يتغير: الـ fixture أدناه يعيد توجيه
# WEBHOOK_DB إلى tmp_path ويعيد تحميل الوحدة لكل اختبار على أي حال.
os.environ.setdefault(
    "WEBHOOK_DB",
    str(Path(tempfile.gettempdir()) / "marathon_webhooks_import_probe.db"),
)

import importlib
import src.webhooks as wh


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    os.environ["WEBHOOK_DB"] = str(tmp_path / "test_webhooks.db")
    importlib.reload(wh)
    wh.init_db()
    yield
    Path(os.environ["WEBHOOK_DB"]).unlink(missing_ok=True)


def test_register_and_list():
    wid = wh.register_webhook(
        "https://example.com/hook", "secret123",
        ["job.completed", "job.failed"],
    )
    assert wid > 0
    hooks = wh.list_webhooks()
    assert len(hooks) == 1
    assert hooks[0]["url"] == "https://example.com/hook"


def test_get_webhooks_for_event():
    wh.register_webhook("https://a.com", "s1", ["job.completed"])
    wh.register_webhook("https://b.com", "s2", ["job.failed"])
    wh.register_webhook("https://c.com", "s3", ["*"])

    completed = wh.get_webhooks_for_event("job.completed")
    assert len(completed) == 2   # a و c

    failed = wh.get_webhooks_for_event("job.failed")
    assert len(failed) == 2      # b و c


def test_delete_webhook():
    wid = wh.register_webhook("https://x.com", "s", ["*"])
    assert wh.delete_webhook(wid) is True
    assert wh.delete_webhook(wid) is False


def test_sign_payload_stable():
    sig1 = wh._sign_payload(b"hello", "secret")
    sig2 = wh._sign_payload(b"hello", "secret")
    assert sig1 == sig2
    assert len(sig1) == 64


def test_sign_payload_differs_with_secret():
    sig1 = wh._sign_payload(b"hello", "secret1")
    sig2 = wh._sign_payload(b"hello", "secret2")
    assert sig1 != sig2


def test_stats_empty():
    stats = wh.webhook_stats()
    assert stats["total_webhooks"] == 0
