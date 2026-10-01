"""مصنع مُهايئات CMS."""
from typing import Optional
from .base import CMSAdapter, PublishResult
from .wordpress import WordPressAdapter
from .notion import NotionAdapter
from .webhook_cms import WebhookCMSAdapter

_ADAPTERS = {
    "wordpress": WordPressAdapter,
    "notion": NotionAdapter,
    "webhook": WebhookCMSAdapter,
}


def create_adapter(cms_type: str, **kwargs) -> Optional[CMSAdapter]:
    """إنشاء مُهايئ من اسمه."""
    cls = _ADAPTERS.get(cms_type.lower())
    if not cls:
        return None
    return cls(**kwargs)
