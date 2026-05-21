"""
OTTO 审核助手 - 数据模型。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


CONTENT_TYPES = {
    "video": "视频",
    "blog": "动态",
    "avatar": "头像",
    "cover": "封面",
}


CONTENT_TYPE_MAP = {
    "video": {
        "list_endpoint": "/api/moderation/videos",
        "approve_endpoint": "/api/moderation/videos/{id}/approve",
        "id_field": "vid",
        "list_key": "video_list",
    },
    "blog": {
        "list_endpoint": "/api/moderation/blogs",
        "approve_endpoint": "/api/moderation/blogs/{id}/approve",
        "id_field": "bid",
        "list_key": "blog_list",
    },
    "avatar": {
        "list_endpoint": "/api/moderation/avatars",
        "approve_endpoint": "/api/moderation/avatars/{id}/approve",
        "id_field": "uid",
        "list_key": "avatar_list",
    },
    "cover": {
        "list_endpoint": "/api/moderation/covers",
        "approve_endpoint": "/api/moderation/covers/{id}/approve",
        "id_field": "uid",
        "list_key": "cover_list",
    },
}


@dataclass
class PluginConfig:
    otto_base_url: str = "https://api.ottohub.cn"
    otto_uid_email: str = ""
    otto_password: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_timeout: int = 60
    llm_api_type: str = "openai"
    auto_execute: bool = True

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "PluginConfig":
        if not isinstance(config, dict):
            config = {}
        return cls(
            otto_base_url=str(config.get("otto_base_url", "https://api.ottohub.cn")).rstrip("/"),
            otto_uid_email=str(config.get("otto_uid_email", "")),
            otto_password=str(config.get("otto_password", "")),
            llm_base_url=str(config.get("llm_base_url", "")).rstrip("/"),
            llm_api_key=str(config.get("llm_api_key", "")),
            llm_model=str(config.get("llm_model", "gpt-4o")),
            llm_timeout=int(config.get("llm_timeout", 60)),
            llm_api_type=str(config.get("llm_api_type", "openai")),
            auto_execute=bool(config.get("auto_execute", True)),
        )
