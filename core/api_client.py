"""OTTO Hub Moderation API 客户端。"""
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

    async def get_audit_list(self, content_type: str, offset: int = 0, num: int = 20) -> List[Dict[str, Any]]:
        type_info = CONTENT_TYPE_MAP.get(content_type)
        if not type_info:
            raise ApiError(f"不支持的内容类型: {content_type}")

        token = await self._get_token()
        url = f"{self.base_url}{type_info['list_endpoint']}"
        params = {"token": token, "offset": str(offset), "num": str(num)}
        list_key = type_info["list_key"]

        logger.info(f"📋 [OTTO] 获取待审{content_type}列表 offset={offset} num={num}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as resp:
                data = await resp.json()

        if data.get("status") == "error":
            raise ApiError(f"获取待审列表失败: {data.get('message')}")

        data_obj = data.get("data", {})
        items = data_obj.get(list_key, [])
        logger.info(f"✅ [OTTO] 获取到 {len(items)} 条待审{content_type}")
        return items

    async def find_audit_item(self, content_type: str, content_id: int) -> Optional[Dict[str, Any]]:
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
        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=payload, timeout=30) as resp:
                data = await resp.json()

        if data.get("status") == "error":
            error_msg = data.get("message", "")
            if error_msg in ("cannot_review_own_content", "cannot_review_own_report"):
                logger.warning(f"⚠️ [OTTO] 回避机制触发: {error_msg}")
            raise ApiError(f"通过失败: {error_msg}")

        logger.info(f"✅ [OTTO] 已通过{content_type} ID={content_id}")
        return True
