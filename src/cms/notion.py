"""مُهايئ Notion عبر API."""
import logging
from typing import List, Optional

import httpx

from .base import CMSAdapter, PublishResult

logger = logging.getLogger(__name__)


class NotionAdapter(CMSAdapter):
    name = "notion"

    def __init__(self, api_token: str, database_id: str):
        self.api = "https://api.notion.com/v1"
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def test_connection(self) -> bool:
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(f"{self.api}/databases/{self.database_id}",
                          headers=self.headers)
                return r.status_code == 200
        except Exception as e:
            logger.error("فشل Notion: %s", e)
            return False

    def publish(self, title: str, content: str,
                tags: List[str] = None, **kwargs) -> PublishResult:
        try:
            # تقسيم المحتوى إلى blocks
            blocks = self._markdown_to_blocks(content)

            payload = {
                "parent": {"database_id": self.database_id},
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": title}}]
                    },
                },
                "children": blocks[:100],   # حد Notion
            }

            if tags:
                payload["properties"]["Tags"] = {
                    "multi_select": [{"name": t} for t in tags]
                }

            with httpx.Client(timeout=60) as c:
                r = c.post(f"{self.api}/pages",
                           headers=self.headers, json=payload)
                r.raise_for_status()
                data = r.json()
                return PublishResult(
                    success=True,
                    url=data.get("url"),
                    post_id=data.get("id"),
                )
        except Exception as e:
            logger.exception("فشل نشر Notion: %s", e)
            return PublishResult(success=False, error=str(e))

    def _markdown_to_blocks(self, md: str) -> List[dict]:
        """تحويل Markdown مبسط إلى blocks."""
        blocks = []
        for line in md.split("\n"):
            line = line.rstrip()
            if not line.strip():
                continue
            if line.startswith("# "):
                blocks.append(self._heading(line[2:], 1))
            elif line.startswith("## "):
                blocks.append(self._heading(line[3:], 2))
            elif line.startswith("### "):
                blocks.append(self._heading(line[4:], 3))
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append(self._bullet(line[2:]))
            elif line.startswith("> "):
                blocks.append(self._quote(line[2:]))
            elif line.startswith("```"):
                continue
            else:
                blocks.append(self._paragraph(line))
        return blocks

    def _paragraph(self, text: str) -> dict:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    def _heading(self, text: str, level: int) -> dict:
        key = f"heading_{level}"
        return {
            "object": "block",
            "type": key,
            key: {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    def _bullet(self, text: str) -> dict:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    def _quote(self, text: str) -> dict:
        return {
            "object": "block",
            "type": "quote",
            "quote": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }
