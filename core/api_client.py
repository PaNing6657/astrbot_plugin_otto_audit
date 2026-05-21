"""OTTO Hub Moderation API 客户端。"""
import time
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
        self._item_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self._cache_ttl: float = 120.0
        self._cache_time: Dict[str, float] = {}

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
        params = {"token": token, "offset": str(offset), "num": str(num)}
        list_key = type_info["list_key"]

        logger.info(f"📋 [OTTO] 获取待审{content_type}列表 offset={offset} num={num}")
        data = await self._request(url, params=params)

        if data.get("status") == "error":
            raise ApiError(f"获取待审列表失败: {data.get('message')}")

        data_obj = data.get("data", {})
        items = data_obj.get(list_key, [])
        logger.info(f"✅ [OTTO] 获取到 {len(items)} 条待审{content_type}")

        self._cache_items(content_type, items)
        return items

    def _cache_items(self, content_type: str, items: List[Dict[str, Any]]) -> None:
        id_field = CONTENT_TYPE_MAP[content_type]["id_field"]
        now = time.time()
        cache = self._item_cache.setdefault(content_type, {})
        for item in items:
            item_id = item.get(id_field)
            if item_id is not None:
                cache[int(item_id)] = dict(item)
        self._cache_time[content_type] = now

    def _get_cached_item(self, content_type: str, content_id: int) -> Optional[Dict[str, Any]]:
        cache = self._item_cache.get(content_type, {})
        cached_time = self._cache_time.get(content_type, 0)
        if time.time() - cached_time > self._cache_ttl:
            return None
        item = cache.get(int(content_id))
        if item:
            return dict(item)
        return None

    async def find_audit_item(self, content_type: str, content_id: int) -> Optional[Dict[str, Any]]:
        cached = self._get_cached_item(content_type, content_id)
        if cached:
            logger.info(f"✅ [OTTO] 从缓存命中{content_type} ID={content_id}")
            return cached
        items = await self.get_audit_list(content_type, offset=0, num=100)
        id_field = CONTENT_TYPE_MAP[content_type]["id_field"]
        for item in items:
            if item.get(id_field) == content_id:
                return item
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
