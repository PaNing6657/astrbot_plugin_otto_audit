"""多模态 AI 审核引擎。"""
import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, Optional
import aiohttp
from astrbot.api import logger

from ..models import PluginConfig


CONTENT_TYPE_LABELS = {
    "video": "视频",
    "blog": "动态",
    "avatar": "头像",
    "cover": "封面",
}


AUDIT_SYSTEM_PROMPT = """你是一个内容审核助手。请根据平台内容审核规范，判断以下内容是否合规。

审核要求：
1. 检查是否包含色情/低俗内容
2. 检查是否包含暴力/恐怖内容
3. 检查是否包含政治敏感内容
4. 检查是否包含广告/垃圾信息
5. 检查是否包含侵权内容
6. 检查是否违反其他法律法规

请以 JSON 格式返回审核结果，格式如下：
{"passed": true, "reason": "内容合规，无违规内容"}
或
{"passed": false, "reason": "具体违规原因描述"}

注意：只返回 JSON，不要返回其他内容。"""


class AuditError(Exception):
    pass


class Auditor:
    def __init__(self, config: PluginConfig):
        self.config = config

    async def audit(self, content_type: str, content_data: Dict[str, Any]) -> Dict[str, Any]:
        if content_type == "video":
            return await self._audit_video(content_data)
        if content_type == "blog":
            return await self._audit_blog(content_data)
        if content_type == "avatar":
            return await self._audit_image(content_type, content_data, "avatar_url")
        if content_type == "cover":
            return await self._audit_image(content_type, content_data, "cover_url")
        raise AuditError(f"不支持的内容类型: {content_type}")

    async def _build_prompt(self, content_type: str, content_data: Dict[str, Any]) -> str:
        label = CONTENT_TYPE_LABELS.get(content_type, content_type)
        prompt_parts = [f"请审核以下{label}内容："]

        if content_type == "video":
            title = content_data.get("title", "")
            intro = content_data.get("intro", "")
            tag = content_data.get("tag", "")
            if title:
                prompt_parts.append(f"标题：{title}")
            if intro:
                prompt_parts.append(f"简介：{intro}")
            if tag:
                prompt_parts.append(f"标签：{tag}")

        elif content_type == "blog":
            title = content_data.get("title", "")
            content = content_data.get("content", "")
            if title:
                prompt_parts.append(f"标题：{title}")
            if content:
                prompt_parts.append(f"内容：{content}")

        return "\n".join(prompt_parts)

    async def _get_image_url(self, content_type: str, content_data: Dict[str, Any]) -> Optional[str]:
        if content_type == "video":
            return content_data.get("cover_url") or content_data.get("video_url")
        if content_type == "avatar":
            return content_data.get("avatar_url")
        if content_type == "cover":
            return content_data.get("cover_url")
        return None

    async def _get_ffprobe_duration(self, video_url: str) -> Optional[float]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_url,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                logger.warning("⏰ ffprobe 超时")
                return None
            if proc.returncode != 0:
                return None
            text = stdout.decode().strip()
            if text:
                return float(text)
        except FileNotFoundError:
            logger.info("⚠️ ffprobe 未安装，跳过视频时长检查")
        except Exception as exc:
            logger.warning(f"⚠️ 获取视频时长失败: {exc}")
        return None

    async def _audit_video(self, content_data: Dict[str, Any]) -> Dict[str, Any]:
        video_url = content_data.get("video_url")
        if video_url:
            duration = await self._get_ffprobe_duration(video_url)
            if duration is not None and duration > 1800:
                logger.info(f"⏭️ [审核] 视频时长 {duration:.0f}秒 超过30分钟，跳过AI审核")
                return {"skip": True, "reason": f"视频时长 {duration:.0f}秒 超过30分钟"}

        text_prompt = await self._build_prompt("video", content_data)
        cover_url = content_data.get("cover_url")
        image_url = cover_url or video_url
        return await self._call_llm(text_prompt, image_url)

    async def _audit_blog(self, content_data: Dict[str, Any]) -> Dict[str, Any]:
        text_prompt = await self._build_prompt("blog", content_data)
        return await self._call_llm(text_prompt, None)

    async def _audit_image(self, content_type: str, content_data: Dict[str, Any], url_field: str) -> Dict[str, Any]:
        text_prompt = await self._build_prompt(content_type, content_data)
        image_url = content_data.get(url_field)
        return await self._call_llm(text_prompt, image_url)

    async def _call_llm(self, text_prompt: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        if not self.config.llm_base_url or not self.config.llm_api_key:
            raise AuditError("LLM 配置不完整，请配置接口地址、API Key 和模型")

        api_type = self.config.llm_api_type
        if api_type == "ark":
            return await self._call_ark(text_prompt, image_url)
        return await self._call_openai(text_prompt, image_url)

    async def _call_openai(self, text_prompt: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        base_url = self.config.llm_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"

        user_content = []
        if image_url:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
        user_content.append({
            "type": "text",
            "text": text_prompt,
        })

        payload = {
            "model": self.config.llm_model,
            "messages": [
                {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.llm_api_key}",
        }

        logger.info(f"🤖 [审核 LLM] 正在调用 {self.config.llm_model} (openai) 进行审核")
        timeout = aiohttp.ClientTimeout(total=self.config.llm_timeout)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise AuditError(f"LLM 调用失败 HTTP {resp.status}: {error_text}")
                result = await resp.json()

        content = ""
        if "choices" in result and result["choices"]:
            content = result["choices"][0].get("message", {}).get("content", "")

        return self._parse_response(content)

    async def _call_ark(self, text_prompt: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        base_url = self.config.llm_base_url.rstrip("/")
        url = f"{base_url}/responses"

        full_text = AUDIT_SYSTEM_PROMPT + "\n\n" + text_prompt

        user_content = []
        if image_url:
            user_content.append({
                "type": "input_image",
                "image_url": image_url,
            })
        user_content.append({
            "type": "input_text",
            "text": full_text,
        })

        payload = {
            "model": self.config.llm_model,
            "input": [
                {"role": "user", "content": user_content},
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.llm_api_key}",
        }

        logger.info(f"🤖 [审核 LLM] 正在调用 {self.config.llm_model} (ark) 进行审核")
        timeout = aiohttp.ClientTimeout(total=self.config.llm_timeout)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise AuditError(f"LLM 调用失败 HTTP {resp.status}: {error_text}")
                result = await resp.json()

        content = ""
        output = result.get("output", [])
        if isinstance(output, list) and output:
            for item in output:
                if isinstance(item, dict):
                    item_content = item.get("content", "")
                    if isinstance(item_content, list):
                        for block in item_content:
                            if isinstance(block, dict) and block.get("type") == "output_text":
                                content += block.get("text", "")
                    elif isinstance(item_content, str):
                        content += item_content

        if not content:
            output_text = result.get("output_text", "")
            if isinstance(output_text, str):
                content = output_text

        return self._parse_response(content)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        if not content:
            raise AuditError("LLM 返回内容为空")

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        try:
            result_json = json.loads(content)
            if "passed" not in result_json:
                raise AuditError(f"LLM 返回缺少 passed 字段: {content}")
            return result_json
        except json.JSONDecodeError:
            raise AuditError(f"LLM 返回不是有效 JSON: {content}")
