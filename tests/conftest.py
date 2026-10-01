# tests/conftest.py
"""إعدادات مشتركة للاختبارات — قواعد بيانات معزولة في مجلد مؤقت."""
import os
import sys
import tempfile
from pathlib import Path

# مجلد المشروع الجذري في sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TMP = tempfile.mkdtemp(prefix="marathon_tests_")

# قواعد بيانات اختبار معزولة (قبل أي استيراد لـ src)
os.environ.setdefault("AUTH_DB", str(Path(_TMP) / "auth.db"))
os.environ.setdefault("AB_DB", str(Path(_TMP) / "ab_testing.db"))
os.environ.setdefault("WEBHOOK_DB", str(Path(_TMP) / "webhooks.db"))
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_pytest_only")
os.environ.setdefault("QUALITY_DB", str(Path(_TMP) / "quality.db"))
