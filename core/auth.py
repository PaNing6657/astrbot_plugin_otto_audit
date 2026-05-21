"""OTTO Hub 登录认证与 token 管理。"""
import time
from typing import Optional, Tuple
import aiohttp
from astrbot.api import logger


class AuthError(Exception):
    pass


class AuthManager:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._uid: Optional[int] = None
        self._is_audit: bool = False
        self._is_admin: bool = False
        self._login_time: float = 0
        self._token_ttl: float = 86400

    @property
    def token(self) -> Optional[str]:
        return self._token

    @property
    def uid(self) -> Optional[int]:
        return self._uid

    @property
    def is_authenticated(self) -> bool:
        if not self._token:
            return False
        if time.time() - self._login_time > self._token_ttl:
            return False
        return True

    @property
    def is_audit(self) -> bool:
        return self._is_audit

    async def login(self, uid_email: str, password: str) -> None:
        if not uid_email or not password:
            raise AuthError("登录凭据未配置")

        url = f"{self.base_url}/api/auth/login"
        payload = {"uid_email": uid_email, "pw": password}

        logger.info(f"🔑 [OTTO] 正在登录 {self.base_url}")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                data = await resp.json()

        if data.get("status") == "error":
            error_msg = data.get("message", "未知错误")
            raise AuthError(f"登录失败: {error_msg}")

        self._token = data.get("token")
        self._uid = data.get("uid")
        self._is_audit = bool(data.get("is_audit", False))
        self._is_admin = bool(data.get("is_admin", False))
        self._login_time = time.time()

        if not self._token:
            raise AuthError("登录成功但未返回 token")

        role = "管理员" if self._is_admin else "审核员" if self._is_audit else "普通用户"
        logger.info(f"✅ [OTTO] 登录成功 UID={self._uid} ({role})")

    async def ensure_login(self, uid_email: str, password: str) -> str:
        if self.is_authenticated:
            return self._token
        await self.login(uid_email, password)
        return self._token
