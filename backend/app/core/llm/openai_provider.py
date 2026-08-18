"""
OpenAI 兼容 Provider

支持 OpenAI 官方 / 国内代理 / Qwen / DeepSeek / GLM 等兼容 OpenAI Chat Completions 协议的服务。

优化点（借鉴 mewcode）：
- 使用 serialization 模块处理消息格式转换
- 使用类型化 StreamEvent（dataclass）替代 dict
- 支持 reasoning_content（DeepSeek/小米等 provider 的思考过程）
- 支持 cache 统计（prompt_tokens_details.cached_tokens）
- 使用分类异常（AuthenticationError/RateLimitError/NetworkError）
"""

import json
import logging
import os
from typing import Optional

import httpx

from .base import (
    LLMProvider, Message, ToolSchema, ToolCall,
    LLMResponse, TokenUsage,
)
from .events import (
    TextDelta, ReasoningDelta, ReasoningComplete,
    ToolCallStart, ToolCallDelta, ToolCallComplete, StreamEnd,
    StreamEvent,
)
from .serialization import (
    build_chat_completion_messages,
    build_tools_for_chat_completion,
    parse_tool_call_arguments,
)
from .errors import (
    AuthenticationError, RateLimitError, NetworkError,
    InvalidRequestError, ContentFilterError, LLMError,
)

logger = logging.getLogger("offerclaw.llm.openai")


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容协议 Provider"""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        # 显式传入的参数优先于环境变量，支持多 provider 实例用不同模型
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = 60.0

        if not self.api_key:
            logger.warning("OpenAIProvider 未配置 OPENAI_API_KEY，调用将失败")

    # ============ 内部辅助 ============

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool = False,
    ) -> dict:
        """构建请求 payload（chat 和 chat_stream 共用）"""
        payload: dict = {
            "model": self.model,
            "messages": build_chat_completion_messages(messages),
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = build_tools_for_chat_completion(tools)
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _extract_usage(self, usage_data: dict) -> TokenUsage:
        """从 API 响应中提取 TokenUsage（含 cache 统计）

        部分兼容 provider 通过 prompt_tokens_details.cached_tokens 上报 cache 命中数，
        大多数不上报（cache_read 保持 0）。prompt_tokens 包含了缓存 token，
        需要减去以保持 prompt + cache_read 可加性。
        """
        prompt_tokens = usage_data.get("prompt_tokens", 0) or 0
        completion_tokens = usage_data.get("completion_tokens", 0) or 0
        total_tokens = usage_data.get("total_tokens", 0) or (prompt_tokens + completion_tokens)

        # cache 命中数（OpenAI 通过 prompt_tokens_details.cached_tokens 暴露）
        details = usage_data.get("prompt_tokens_details") or {}
        cache_read = 0
        if isinstance(details, dict):
            cache_read = details.get("cached_tokens", 0) or 0

        # prompt_tokens 包含了 cache 命中的 token，需要减去以保持可加性
        if cache_read:
            prompt_tokens = max(prompt_tokens - cache_read, 0)

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_read=cache_read,
            cache_creation=0,  # OpenAI 系列不暴露 creation 计数
        )

    def _handle_http_error(self, e: httpx.HTTPStatusError) -> None:
        """把 HTTP 错误转换为分类异常"""
        status = e.response.status_code
        body = e.response.text[:500]

        if status == 401:
            raise AuthenticationError(
                f"API Key 无效或已过期: {body}",
                provider=self.name,
                status_code=status,
            ) from e
        if status == 429:
            retry_after = None
            retry_header = e.response.headers.get("retry-after") or e.response.headers.get("Retry-After")
            if retry_header:
                try:
                    retry_after = float(retry_header)
                except (ValueError, TypeError):
                    pass
            raise RateLimitError(
                f"请求被限流: {body}",
                retry_after=retry_after,
                provider=self.name,
                status_code=status,
            ) from e
        if status in (400,):
            # 内容审核拦截通常返回 400 + 特定错误码
            if "content_filter" in body.lower() or "sensitive" in body.lower():
                raise ContentFilterError(
                    f"内容被审核拦截: {body}",
                    provider=self.name,
                    status_code=status,
                ) from e
            raise InvalidRequestError(
                f"请求格式错误: {body}",
                provider=self.name,
                status_code=status,
            ) from e
        if status in (403,):
            raise AuthenticationError(
                f"无访问权限: {body}",
                provider=self.name,
                status_code=status,
            ) from e
        # 5xx 和其他错误
        raise LLMError(
            f"API 错误 (HTTP {status}): {body}",
            provider=self.name,
            status_code=status,
        ) from e

    def _handle_network_error(self, e: Exception) -> None:
        """把网络异常转换为 NetworkError"""
        raise NetworkError(
            f"网络错误 ({type(e).__name__}): {e}",
            provider=self.name,
        ) from e

    # ============ chat（非流式）============

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        payload = self._build_payload(messages, tools, temperature, max_tokens, stream=False)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]

            tool_calls = []
            for tc in msg.get("tool_calls", []) or []:
                fn = tc["function"]
                raw_args = fn["arguments"]
                if isinstance(raw_args, str):
                    args = parse_tool_call_arguments(raw_args)
                else:
                    args = raw_args if isinstance(raw_args, dict) else {}
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=fn["name"],
                    arguments=args,
                ))

            usage = self._extract_usage(data.get("usage", {}))
            return LLMResponse(
                content=msg.get("content"),
                tool_calls=tool_calls,
                finish_reason=choice.get("finish_reason", "stop"),
                usage=usage,
            )

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                httpx.PoolTimeout, httpx.ConnectTimeout) as e:
            self._handle_network_error(e)

    # ============ chat_stream（流式）============

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> "StreamEvent":
        """流式输出，yield 类型化 StreamEvent

        事件序列：
        - TextDelta: 文本内容增量
        - ReasoningDelta: 推理过程增量（DeepSeek reasoning_content）
        - ReasoningComplete: 推理过程完成
        - ToolCallStart: 工具调用开始
        - ToolCallDelta: 工具参数增量
        - ToolCallComplete: 工具调用完成
        - StreamEnd: 流结束（含 usage）
        """
        payload = self._build_payload(messages, tools, temperature, max_tokens, stream=True)

        # 流式 tool_call 状态：按 index 累积
        # Chat Completions 流按 tool_calls 列表中的位置索引下发 delta
        active_calls: dict[int, dict[str, str]] = {}  # index -> {id, name, args}
        reasoning_accum = ""
        finish_reason = "stop"
        usage = TokenUsage()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
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

                        # usage 数据（最后一个 chunk，choices 为空）
                        if not chunk.get("choices"):
                            if chunk.get("usage"):
                                usage = self._extract_usage(chunk["usage"])
                            continue

                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {})

                        # --- 文本内容 ---
                        content = delta.get("content")
                        if content:
                            yield TextDelta(text=content)

                        # --- reasoning_content（DeepSeek/小米等 provider 的非标准字段）---
                        rc = delta.get("reasoning_content")
                        if rc:
                            reasoning_accum += rc
                            yield ReasoningDelta(text=rc)

                        # --- tool_call 增量 ---
                        if delta.get("tool_calls"):
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in active_calls:
                                    active_calls[idx] = {"id": "", "name": "", "args": ""}
                                    # 首个 chunk 带 id 和 name
                                    call_id = tc_delta.get("id", "")
                                    fn = tc_delta.get("function", {}) or {}
                                    call_name = fn.get("name", "")
                                    if call_id:
                                        active_calls[idx]["id"] = call_id
                                    if call_name:
                                        active_calls[idx]["name"] = call_name
                                    yield ToolCallStart(
                                        tool_name=active_calls[idx]["name"],
                                        tool_id=active_calls[idx]["id"],
                                    )
                                else:
                                    # 后续 chunk 可能补全 id/name
                                    if tc_delta.get("id"):
                                        active_calls[idx]["id"] = tc_delta["id"]
                                    fn = tc_delta.get("function", {}) or {}
                                    if fn.get("name"):
                                        active_calls[idx]["name"] = fn["name"]

                                # 累积参数片段
                                fn = tc_delta.get("function", {}) or {}
                                args_delta = fn.get("arguments", "")
                                if args_delta:
                                    active_calls[idx]["args"] += args_delta
                                    yield ToolCallDelta(text=args_delta)

                        # --- 结束原因 ---
                        fr = choice.get("finish_reason")
                        if fr:
                            finish_reason = fr

            # --- 流结束，发射完成事件 ---

            # 推理过程完成
            if reasoning_accum:
                yield ReasoningComplete(reasoning=reasoning_accum, signature="")

            # tool_call 完成
            if finish_reason == "tool_calls":
                for idx in sorted(active_calls.keys()):
                    call = active_calls[idx]
                    args = parse_tool_call_arguments(call["args"])
                    yield ToolCallComplete(
                        tool_id=call["id"],
                        tool_name=call["name"],
                        arguments=args,
                    )

            yield StreamEnd(
                finish_reason=finish_reason,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cache_read=usage.cache_read,
                cache_creation=usage.cache_creation,
            )

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                httpx.PoolTimeout, httpx.ConnectTimeout) as e:
            self._handle_network_error(e)
        except Exception as e:
            logger.error(f"OpenAI 流式调用未知错误: {type(e).__name__}: {e}")
            raise LLMError(f"流式调用失败: {e}", provider=self.name) from e
