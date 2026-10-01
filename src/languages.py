"""إدارة اللغات المتعددة."""
import logging
from pathlib import Path
from typing import Optional, Dict, List

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/languages.yaml")


class LanguageRegistry:
    def __init__(self, path: Path = CONFIG_PATH):
        with open(path, encoding="utf-8") as f:
            self.data = yaml.safe_load(f)["languages"]

    def get(self, code: str) -> Optional[Dict]:
        return self.data.get(code)

    def list_all(self) -> List[str]:
        return list(self.data.keys())

    def is_rtl(self, code: str) -> bool:
        return self.data.get(code, {}).get("rtl", False)

    def get_model_id(self, lang: str, engine: str) -> Optional[str]:
        return self.data.get(lang, {}).get("models", {}).get(engine)

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
