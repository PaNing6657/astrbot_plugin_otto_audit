"""OTTOhub Moderation API 客户端。"""
import difflib
from typing import Any, Dict, List, Optional
import aiohttp
from astrbot.api import logger

from .auth import AuthManager
from ..models import CONTENT_TYPE_MAP


class ApiError(Exception):
    pass


class ModerationClient:
    def __init__(self, base_url: str, auth: AuthManager):
        self.base_url = base_url.rstrip("/")
        self.auth = auth

    async def _get_token(self) -> str:
        token = self.auth.token
        if not token:
            raise ApiError("未登录，请先配置并登录")
        return token

    async def _request(self, url: str, params: Optional[dict] = None, json_body: Optional[dict] = None, method: str = "GET") -> Any:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        raise ApiError(f"HTTP {resp.status}: {text[:200]}")
                    return await resp.json()
            else:
                async with session.request(method, url, json=json_body, timeout=30) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        raise ApiError(f"HTTP {resp.status}: {text[:200]}")
                    return await resp.json()

    async def get_audit_list(self, content_type: str, offset: int = 0, num: int = 20) -> List[Dict[str, Any]]:
        type_info = CONTENT_TYPE_MAP.get(content_type)
        if not type_info:
            raise ApiError(f"不支持的内容类型: {content_type}")

        token = await self._get_token()
        url = f"{self.base_url}{type_info['list_endpoint']}"
        list_key = type_info["list_key"]

        all_items: List[Dict[str, Any]] = []
        current_offset = offset
        page_size = min(num, 10)

        while True:
            params = {"token": token, "offset": str(current_offset), "num": str(page_size)}
            logger.info(f"📋 [OTTO] 获取待审{content_type}列表 offset={current_offset} num={page_size}")
            data = await self._request(url, params=params)

            if data.get("status") == "error":
                raise ApiError(f"获取待审列表失败: {data.get('message')}")

            data_obj = data.get("data", {})
            items = data_obj.get(list_key, [])
            logger.info(f"✅ [OTTO] 获取到 {len(items)} 条待审{content_type}")

            all_items.extend(items)

            if len(items) < 10:
                break

            current_offset += page_size

        logger.info(f"📦 [OTTO] 共获取 {len(all_items)} 条待审{content_type}")
        return all_items

    async def find_audit_item(self, content_type: str, content_id: int) -> Optional[Dict[str, Any]]:
        items = await self.get_audit_list(content_type, offset=0, num=10)
        id_field = CONTENT_TYPE_MAP[content_type]["id_field"]
        for item in items:
            if str(item.get(id_field, "") or "") == str(content_id):
                return item
        return None

    async def find_item_by_title(self, content_type: str, title: str) -> Optional[Dict[str, Any]]:
        items = await self.get_audit_list(content_type, offset=0, num=10)
        title_clean = title.strip().lower()
        matches = []
        for item in items:
            item_title = str(item.get("title", "") or "").strip().lower()
            item_content = str(item.get("content", "") or "").strip().lower()
            item_username = str(item.get("username", "") or "").strip().lower()
            candidates = [item_title, item_content, item_username]
            best_ratio = max(
                difflib.SequenceMatcher(None, title_clean, c).ratio() for c in candidates
            )
            has_full_match = any(title_clean in c for c in candidates)
            if best_ratio >= 0.75 or has_full_match:
                matches.append((item, best_ratio))
        if len(matches) == 1:
            return matches[0][0]
        if len(matches) > 1:
            raise ApiError(f"标题匹配到 {len(matches)} 条结果（相似度≥75%），请提供准确的 ID")
        return None

    async def approve(self, content_type: str, content_id: int) -> bool:
        type_info = CONTENT_TYPE_MAP.get(content_type)
        if not type_info:
            raise ApiError(f"不支持的内容类型: {content_type}")

        token = await self._get_token()
        endpoint = type_info["approve_endpoint"].format(id=content_id)
        url = f"{self.base_url}{endpoint}"
        payload = {"token": token}

        logger.info(f"✅ [OTTO] 正在通过{content_type} ID={content_id}")
        data = await self._request(url, json_body=payload, method="PUT")

        if data.get("status") == "error":
            error_msg = data.get("message", "")
            if error_msg in ("cannot_review_own_content", "cannot_review_own_report"):
                logger.warning(f"⚠️ [OTTO] 回避机制触发: {error_msg}")
            raise ApiError(f"通过失败: {error_msg}")

        logger.info(f"✅ [OTTO] 已通过{content_type} ID={content_id}")
        return True
