"""
OTTO 审核助手插件 - 主逻辑。

工作流程：
1. 用户通过 AI 发出审核指令
2. AI 调用 LLM Tool `audit_content`
3. 插件获取 OTTO Hub 待审内容
4. 调用多模态 LLM 审核
5. 合规 → 自动通过；不合规 → 提示人工复核
"""

import json
import os
import uuid
from typing import Any, AsyncGenerator, Dict, Optional

from quart import jsonify, request

try:
    from astrbot.api.star import Context, Star, register
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.message_components import Plain
    from astrbot.api import llm_tool, logger
except ImportError:
    from astrbot.api.star import Context, Star, register
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.event.components import Plain
    from astrbot.api import llm_tool
    from astrbot.api.utils import logger

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except Exception:
    def get_astrbot_data_path() -> str:
        return os.path.join(os.getcwd(), "data")

from .models import PluginConfig, CONTENT_TYPES, CONTENT_TYPE_MAP
from .core.auth import AuthManager, AuthError
from .core.api_client import ModerationClient, ApiError
from .core.auditor import Auditor, AuditError

PLUGIN_NAME = "astrbot_plugin_otto_audit"
PLUGIN_AUTHOR = "OTTO"
PLUGIN_VERSION = "1.0.0"


@register(PLUGIN_NAME, PLUGIN_AUTHOR, f"OTTO 审核助手 v{PLUGIN_VERSION}", PLUGIN_VERSION)
class OttoAuditPlugin(Star):
    def __init__(self, context: Context, config: Optional[dict] = None):
        super().__init__(context)
        base_data_dir = str(get_astrbot_data_path())
        self.data_dir = os.path.join(base_data_dir, "plugin_data", PLUGIN_NAME)
        os.makedirs(self.data_dir, exist_ok=True)
        self.config_path = os.path.join(self.data_dir, "otto_audit_config.json")

        plugin_config = PluginConfig.from_dict(
            self._load_merged_config(config if isinstance(config, dict) else {})
        )
        self.plugin_config = plugin_config
        self.auth = AuthManager(self.plugin_config.otto_base_url)
        self.api = ModerationClient(self.plugin_config.otto_base_url, self.auth)
        self.auditor = Auditor(self.plugin_config)

        self.context.register_web_api(
            f"/{PLUGIN_NAME}/get_config",
            self.get_config_handler,
            ["GET"],
            "获取 OTTO 审核助手配置",
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/save_config",
            self.save_config_handler,
            ["POST"],
            "保存 OTTO 审核助手配置",
        )

        logger.info(f"[{PLUGIN_NAME}] 插件初始化完成")

    def _load_merged_config(self, native_config: Dict[str, Any]) -> Dict[str, Any]:
        merged = {}
        if native_config:
            merged.update(native_config)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    persisted = json.load(f)
                if isinstance(persisted, dict):
                    persisted.update({k: v for k, v in merged.items() if v})
                    merged = persisted
            except Exception as exc:
                logger.error(f"[{PLUGIN_NAME}] 读取持久化配置失败: {exc}")
        return merged

    def _persist_config(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        tmp_path = f"{self.config_path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({
                    "otto_base_url": self.plugin_config.otto_base_url,
                    "otto_uid_email": self.plugin_config.otto_uid_email,
                    "otto_password": self.plugin_config.otto_password,
                    "llm_base_url": self.plugin_config.llm_base_url,
                    "llm_api_key": self.plugin_config.llm_api_key,
                    "llm_model": self.plugin_config.llm_model,
                    "llm_api_type": self.plugin_config.llm_api_type,
                    "llm_timeout": self.plugin_config.llm_timeout,
                    "auto_execute": self.plugin_config.auto_execute,
                }, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config_path)
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}] 保存配置失败: {exc}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _config_for_page(self) -> Dict[str, Any]:
        return {
            "otto_base_url": self.plugin_config.otto_base_url,
            "otto_uid_email": self.plugin_config.otto_uid_email,
            "otto_password": self.plugin_config.otto_password,
            "llm_base_url": self.plugin_config.llm_base_url,
            "llm_api_key": self.plugin_config.llm_api_key,
            "llm_model": self.plugin_config.llm_model,
            "llm_api_type": self.plugin_config.llm_api_type,
            "llm_timeout": self.plugin_config.llm_timeout,
            "auto_execute": self.plugin_config.auto_execute,
        }

    async def get_config_handler(self):
        return jsonify(self._config_for_page())

    async def save_config_handler(self):
        new_config = await request.get_json(silent=True)
        if not isinstance(new_config, dict):
            return jsonify({"success": False, "message": "配置格式错误"}), 400

        self.plugin_config = PluginConfig.from_dict(new_config)
        self.auth = AuthManager(self.plugin_config.otto_base_url)
        self.api = ModerationClient(self.plugin_config.otto_base_url, self.auth)
        self.auditor = Auditor(self.plugin_config)
        self._persist_config()
        logger.info(f"[{PLUGIN_NAME}] 配置已保存并热重载")
        return jsonify({"success": True, "message": "配置已保存"})

    # ========== Core Logic ==========

    async def _ensure_authenticated(self) -> str:
        return await self.auth.ensure_login(
            self.plugin_config.otto_uid_email,
            self.plugin_config.otto_password,
        )

    async def _audit_and_act(self, content_type: str, content_id: int) -> str:
        await self._ensure_authenticated()

        if not self.auth.is_audit:
            return f"❌ 当前账号不是审核员 (UID={self.auth.uid})，无法执行审核操作"

        logger.info(f"🔍 [审核] 查找待审{content_type} ID={content_id}")
        item = await self.api.find_audit_item(content_type, content_id)

        if not item:
            return f"❌ 未找到待审的{CONTENT_TYPES.get(content_type, content_type)} (ID={content_id})，可能已被审核或不存在"

        logger.info(f"🔍 [审核] 获取到内容，正在调用 LLM 审核")
        result = await self.auditor.audit(content_type, item)

        if result.get("passed"):
            if self.plugin_config.auto_execute:
                try:
                    await self.api.approve(content_type, content_id)
                    return f"✅ 审核通过。AI 判定内容合规（{result.get('reason', '')}），已自动通过审核。"
                except ApiError as e:
                    return f"✅ AI 判定内容合规，但自动通过操作失败: {e}"
            else:
                return f"✅ AI 判定内容合规，等待手动处理。"
        else:
            reason = result.get("reason", "存在违规")
            return f"⚠️ AI 认为存在违规内容：{reason}。请耐心等待人工复核。"

    # ========== LLM Tools ==========

    @llm_tool(name="audit_content")
    async def tool_audit_content(
        self,
        event: AstrMessageEvent,
        audit_type: str,
        target_id: int,
    ) -> str:
        """
        审核 OTTO Hub 上的内容。调用后自动获取内容、调用多模态 AI 审核。合规内容直接通过，存在违规则标记并提示人工复核。
        Args:
            audit_type (string): 内容类型, 可选: video(视频)/blog(动态)/avatar(头像)/cover(封面)
            target_id (int): 内容 ID。video 通过 vid 查找; blog 通过 bid 查找; avatar 通过用户 uid 查找; cover 通过用户 uid 查找
        """
        try:
            audit_type = str(audit_type).strip().lower()
            target_id = int(target_id)

            if audit_type not in CONTENT_TYPES:
                return f"❌ 不支持的内容类型：{audit_type}，可选: {', '.join(CONTENT_TYPES.keys())}"

            return await self._audit_and_act(audit_type, target_id)

        except AuthError as e:
            return f"❌ 认证失败: {e}"
        except ApiError as e:
            return f"❌ API 错误: {e}"
        except AuditError as e:
            return f"❌ 审核引擎错误: {e}"
        except ValueError:
            return "❌ content_id 必须是数字"
        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] audit_content 异常: {e}", exc_info=True)
            return f"❌ 审核过程发生异常: {e}"

    @llm_tool(name="audit_list")
    async def tool_audit_list(
        self,
        event: AstrMessageEvent,
        audit_type: str = "",
        num: int = 10,
    ) -> str:
        """
        获取 OTTO Hub 上的待审核内容列表。
        Args:
            audit_type (string): 内容类型筛选, 可选: video/blog/avatar/cover, 为空则返回全部类型概览
            num (int): 每类型获取的数量，默认10
        """
        try:
            await self._ensure_authenticated()

            if not self.auth.is_audit:
                return "❌ 当前账号不是审核员，无法查看待审列表"

            audit_type = str(audit_type).strip().lower() if audit_type else ""

            if audit_type and audit_type not in CONTENT_TYPES:
                return f"❌ 不支持的内容类型：{audit_type}，可选: {', '.join(CONTENT_TYPES.keys())}"

            types_to_fetch = [audit_type] if audit_type else list(CONTENT_TYPES.keys())
            num = max(1, min(100, int(num)))

            lines = ["📋 OTTO 待审核内容列表："]
            for ct in types_to_fetch:
                items = await self.api.get_audit_list(ct, offset=0, num=num)
                id_field = CONTENT_TYPE_MAP[ct]["id_field"]
                label = CONTENT_TYPES[ct]

                if not items:
                    lines.append(f"\n[{label}] 暂无待审内容")
                    continue

                lines.append(f"\n[{label}] 待审 {len(items)} 条：")
                for item in items:
                    item_id = item.get(id_field, "?")
                    if ct == "video":
                        title = item.get("title", "无标题")
                        lines.append(f"  ID={item_id} | {title}")
                    elif ct in ("avatar", "cover"):
                        username = item.get("username", "未知用户")
                        lines.append(f"  UID={item_id} | {username}")
                    else:
                        title = item.get("title", item.get("content", ""))[:50]
                        lines.append(f"  ID={item_id} | {title}")

                if len(items) >= num:
                    lines.append(f"  ... (仅显示前 {num} 条)")

            return "\n".join(lines)

        except AuthError as e:
            return f"❌ 认证失败: {e}"
        except ApiError as e:
            return f"❌ API 错误: {e}"
        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] audit_list 异常: {e}", exc_info=True)
            return f"❌ 获取审核列表失败: {e}"

    # ========== Commands ==========

    @filter.command("审核")
    async def cmd_audit(
        self,
        event: AstrMessageEvent,
        p1: str = "",
        p2: str = "",
        p3: str = "",
    ) -> AsyncGenerator[Any, None]:
        parts = [p for p in [p1, p2, p3] if p]
        if not parts:
            yield event.plain_result(
                "用法:\n"
                "/审核 视频/动态/头像/封面 ID\n"
                "/审核列表 [类型]\n"
                "示例: /审核 视频 123"
            )
            return

        cmd = parts[0].lower()
        if cmd == "列表":
            ct = parts[1].lower() if len(parts) > 1 else ""
            result = await self.tool_audit_list(event, audit_type=ct, num=10)
            yield event.plain_result(result)
            return

        if len(parts) < 2:
            yield event.plain_result("缺少 ID，用法: /审核 视频/动态/头像/封面 ID")
            return

        type_map = {
            "视频": "video", "video": "video",
            "动态": "blog", "blog": "blog",
            "头像": "avatar", "avatar": "avatar",
            "封面": "cover", "cover": "cover",
        }
        ct = type_map.get(parts[0].lower())
        if not ct:
            yield event.plain_result(f"不支持的类型: {parts[0]}，可选: 视频/动态/头像/封面")
            return

        try:
            content_id = int(parts[1])
        except ValueError:
            yield event.plain_result("ID 必须是数字")
            return

        yield event.plain_result(await self._audit_and_act(ct, content_id))

    @filter.command("审核列表")
    async def cmd_audit_list(
        self,
        event: AstrMessageEvent,
        p1: str = "",
    ) -> AsyncGenerator[Any, None]:
        ct = p1.strip().lower() if p1 else ""
        yield event.plain_result(await self.tool_audit_list(event, audit_type=ct, num=10))
