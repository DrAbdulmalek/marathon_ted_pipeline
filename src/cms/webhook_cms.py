"""مُهايئ عام يرسل المحتوى لأي endpoint (Ghost, Strapi, custom)."""
import logging
from typing import List

import httpx

from .base import CMSAdapter, PublishResult

logger = logging.getLogger(__name__)


class WebhookCMSAdapter(CMSAdapter):
    name = "webhook"

    def __init__(self, url: str, headers: dict = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    def test_connection(self) -> bool:
        try:
            with httpx.Client(timeout=10) as c:
                r = c.post(self.url, json={"test": True},
                           headers=self.headers)
                return r.status_code < 500
        except Exception:
            return False

    def publish(self, title: str, content: str,
                tags: List[str] = None, **kwargs) -> PublishResult:
        try:
            payload = {
                "title": title,
                "content": content,
                "tags": tags or [],
                **kwargs,
            }
            with httpx.Client(timeout=60) as c:
                r = c.post(self.url, json=payload, headers=self.headers)
                r.raise_for_status()
                data = r.json() if r.text else {}
                return PublishResult(
                    success=True,
                    url=data.get("url"),
                    post_id=data.get("id"),
                )
        except Exception as e:
            logger.exception("فشل webhook CMS: %s", e)
            return PublishResult(success=False, error=str(e))
