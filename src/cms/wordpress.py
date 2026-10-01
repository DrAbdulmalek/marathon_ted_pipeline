"""مُهايئ WordPress عبر REST API."""
import logging
import base64
from typing import List, Optional

import httpx

from .base import CMSAdapter, PublishResult

logger = logging.getLogger(__name__)


class WordPressAdapter(CMSAdapter):
    name = "wordpress"

    def __init__(self, site_url: str, username: str, app_password: str):
        self.site_url = site_url.rstrip("/")
        self.api = f"{self.site_url}/wp-json/wp/v2"
        creds = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

    def test_connection(self) -> bool:
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(f"{self.api}/users/me", headers=self.headers)
                return r.status_code == 200
        except Exception as e:
            logger.error("فشل الاتصال بـ WordPress: %s", e)
            return False

    def publish(self, title: str, content: str,
                tags: List[str] = None, **kwargs) -> PublishResult:
        try:
            payload = {
                "title": title,
                "content": content,
                "status": kwargs.get("status", "draft"),
                "format": kwargs.get("format", "standard"),
            }

            # كلمات مفتاحية
            if tags:
                tag_ids = self._get_or_create_tags(tags)
                if tag_ids:
                    payload["tags"] = tag_ids

            # فئة
            if cat := kwargs.get("category"):
                payload["categories"] = [self._get_category_id(cat)]

            with httpx.Client(timeout=60) as c:
                r = c.post(f"{self.api}/posts",
                           headers=self.headers, json=payload)
                r.raise_for_status()
                data = r.json()
                return PublishResult(
                    success=True,
                    url=data.get("link"),
                    post_id=str(data.get("id")),
                )
        except Exception as e:
            logger.exception("فشل نشر WordPress: %s", e)
            return PublishResult(success=False, error=str(e))

    def _get_or_create_tags(self, tags: List[str]) -> List[int]:
        ids = []
        with httpx.Client(timeout=15) as c:
            for tag in tags:
                r = c.get(f"{self.api}/tags",
                          headers=self.headers, params={"search": tag})
                if r.status_code == 200 and r.json():
                    ids.append(r.json()[0]["id"])
                else:
                    r = c.post(f"{self.api}/tags",
                               headers=self.headers, json={"name": tag})
                    if r.status_code == 201:
                        ids.append(r.json()["id"])
        return ids

    def _get_category_id(self, name: str) -> Optional[int]:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{self.api}/categories",
                      headers=self.headers, params={"search": name})
            if r.status_code == 200 and r.json():
                return r.json()[0]["id"]
        return None
