"""
OpenAI 兼容 Provider
支持 OpenAI 官方 / 国内代理 / Qwen 等兼容 OpenAI 协议的服务
"""

import os
import json
import logging
from typing import Optional

import httpx

from .base import (
    LLMProvider, Message, ToolSchema, ToolCall,
    LLMResponse, TokenUsage,
)

logger = logging.getLogger("offerclaw.llm.openai")


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容协议 Provider"""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", model)
        self.timeout = 60.0

        if not self.api_key:
            logger.warning("OpenAIProvider 未配置 OPENAI_API_KEY，调用将失败")

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]

            tool_calls = []
            for tc in msg.get("tool_calls", []) or []:
                fn = tc["function"]
                # arguments 是 JSON 字符串，需要解析
                try:
                    args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                except json.JSONDecodeError:
                    args = {"_raw": fn["arguments"]}
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=fn["name"],
                    arguments=args,
                ))

            usage = data.get("usage", {})
            return LLMResponse(
                content=msg.get("content"),
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", "stop"),
                usage=TokenUsage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                ),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        """流式输出（SSE 解析）"""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 累积 tool_call（流式时按 index 分片到达）
        tool_call_acc: dict[int, dict] = {}
        finish_reason = "stop"
        usage = TokenUsage()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield {"type": "content", "delta": delta["content"]}
                        if "tool_calls" in delta and delta["tool_calls"]:
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_call_acc:
                                    tool_call_acc[idx] = {
                                        "id": tc_delta.get("id", ""),
                                        "name": tc_delta.get("function", {}).get("name", ""),
                                        "arguments": "",
                                    }
                                else:
                                    if tc_delta.get("id"):
                                        tool_call_acc[idx]["id"] = tc_delta["id"]
                                    if tc_delta.get("function", {}).get("name"):
                                        tool_call_acc[idx]["name"] = tc_delta["function"]["name"]
                                tool_call_acc[idx]["arguments"] += tc_delta.get("function", {}).get("arguments", "")
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]
                        if chunk.get("usage"):
                            u = chunk["usage"]
                            usage = TokenUsage(
                                prompt_tokens=u.get("prompt_tokens", 0),
                                completion_tokens=u.get("completion_tokens", 0),
                                total_tokens=u.get("total_tokens", 0),
                            )

            # 流结束，发射完整 tool_calls
            for idx in sorted(tool_call_acc.keys()):
                tc = tool_call_acc[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {"_raw": tc["arguments"]}
                yield {
                    "type": "tool_call",
                    "tool_call": ToolCall(id=tc["id"], name=tc["name"], arguments=args),
                }

            yield {"type": "done", "usage": usage, "finish_reason": finish_reason}

        except Exception as e:
            logger.error(f"OpenAI 流式调用失败: {e}")
            raise
