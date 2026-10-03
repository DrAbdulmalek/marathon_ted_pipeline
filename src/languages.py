"""إدارة اللغات المتعددة."""
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List

import yaml

logger = logging.getLogger(__name__)

#: مسار **مطلق** مشتق من موقع هذا الملف.
#: كان `Path("config/languages.yaml")` نسبياً، فكان `get_registry()` يفشل
#: بـ FileNotFoundError كلما لم يكن CWD هو جذر المستودع (systemd، Docker،
#: pytest من مجلد آخر، أي سكربت يُستدعى من مسار مختلف). مُثبت في تقرير التدقيق.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "languages.yaml"

#: يمكن التجاوز بمتغير البيئة LANGUAGES_FILE (للاختبار وللتوزيعات المخصصة).
CONFIG_PATH = Path(os.getenv("LANGUAGES_FILE") or _DEFAULT_CONFIG_PATH)


class LanguageRegistry:
    def __init__(self, path: Optional[Path] = None):
        # يُقرأ LANGUAGES_FILE لحظة الإنشاء لا لحظة الاستيراد، حتى يعمل التجاوز
        # في الاختبارات وفي العمليات طويلة العمر.
        resolved = Path(path or os.getenv("LANGUAGES_FILE") or CONFIG_PATH)
        self.path = resolved
        with open(resolved, encoding="utf-8") as f:
            self.data = yaml.safe_load(f)["languages"]

    def get(self, code: str) -> Optional[Dict]:
        return self.data.get(code)

    def list_all(self) -> List[str]:
        return list(self.data.keys())

    def is_rtl(self, code: str) -> bool:
        return self.data.get(code, {}).get("rtl", False)

    def get_model_id(self, lang: str, engine: str) -> Optional[str]:
        return self.data.get(lang, {}).get("models", {}).get(engine)

    def is_source_only(self, code: str) -> bool:
        """لغة مصدر فقط (مثل `en`): موجودة في السجل لكنها لا تحتاج نموذج ترجمة إليها.

        الفائدة: تمنع `MultiLangTranslator._get_backend` من رفع ValueError على لغة
        مصدر، وتسمح للـ API بأن يعرضها كلغة إدخال صالحة.
        """
        return bool(self.data.get(code, {}).get("source_only", False))

    def supported_for_engine(self, engine: str) -> List[str]:
        return [
            code for code, info in self.data.items()
            if engine in info.get("models", {})
        ]


_registry: Optional[LanguageRegistry] = None


def get_registry() -> LanguageRegistry:
    global _registry
    if _registry is None:
        _registry = LanguageRegistry()
    return _registry
