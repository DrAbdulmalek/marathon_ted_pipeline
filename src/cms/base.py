"""الواجهة الموحدة لتكامل CMS."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class PublishResult:
    success: bool
    url: Optional[str] = None
    post_id: Optional[str] = None
    error: Optional[str] = None


class CMSAdapter(ABC):
    """الواجهة الأساسية لكل مُهايئ CMS."""

    name: str = "base"

    @abstractmethod
    def publish(self, title: str, content: str,
                tags: List[str] = None, **kwargs) -> PublishResult:
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        ...

    def close(self):
        pass
