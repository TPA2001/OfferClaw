"""
可重试的 LLM Provider 装饰器

对底层 LLMProvider 的 chat / chat_stream 做指数退避重试，
覆盖网络抖动、429 限流、5xx 服务端错误。

不重试的场景：
- 4xx 客户端错误（除 429 外）：鉴权失败、请求格式错误等，重试无意义
- 内容审核拦截：重试同样会被拒
- 超过 max_steps 的业务逻辑错误
"""

import asyncio
import logging
from typing import Optional

import httpx

from .base import LLMProvider, Message, ToolSchema, LLMResponse

logger = logging.getLogger("offerclaw.llm.retry")


# 可重试的 HTTP 状态码
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class RetriableLLMProvider(LLMProvider):
    """可重试的 LLM Provider 装饰器

    包装任意 LLMProvider，对其 chat / chat_stream 方法做指数退避重试。

    用法：
        provider = RetriableLLMProvider(OpenAIProvider(), max_retries=3)
    """

    def __init__(
        self,
        inner: LLMProvider,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.inner = inner
        self.name = inner.name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.inner.chat(messages, tools, temperature, max_tokens)
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code not in RETRYABLE_STATUS:
                    # 不可重试的 HTTP 错误，直接抛出
                    logger.error(f"LLM 调用失败（不可重试，HTTP {status_code}）: {e.response.text[:200]}")
                    raise
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, e.response.headers)
                    logger.warning(
                        f"LLM 调用返回 HTTP {status_code}，{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM 调用重试 {self.max_retries} 次后仍失败（HTTP {status_code}）")
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                    httpx.PoolTimeout, httpx.ConnectTimeout, asyncio.TimeoutError) as e:
                # 网络错误可重试
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, {})
                    logger.warning(
                        f"LLM 调用网络错误（{type(e).__name__}），{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM 调用重试 {self.max_retries} 次后仍失败（网络错误）")
            except Exception as e:
                # 未知异常不重试，直接抛出
                logger.error(f"LLM 调用未知异常（不重试）: {type(e).__name__}: {e}")
                raise

        # 重试耗尽，抛出最后一个异常
        raise last_exc

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        """流式调用 - 重试仅覆盖建立连接阶段

        一旦开始接收数据 chunk，不再重试（避免重复输出）。
        """
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                started = False
                async for chunk in self.inner.chat_stream(messages, tools, temperature, max_tokens):
                    started = True
                    yield chunk
                # 正常完成，退出重试循环
                return
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code not in RETRYABLE_STATUS or started:
                    # 不可重试 或 已开始流式输出后出错，不重试
                    raise
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, e.response.headers)
                    logger.warning(
                        f"LLM 流式调用返回 HTTP {status_code}，{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM 流式调用重试 {self.max_retries} 次后仍失败（HTTP {status_code}）")
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                    httpx.PoolTimeout, httpx.ConnectTimeout, asyncio.TimeoutError) as e:
                if started:
                    # 已开始流式输出后断连，不重试（避免重复）
                    raise
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, {})
                    logger.warning(
                        f"LLM 流式调用网络错误（{type(e).__name__}），{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"LLM 流式调用重试 {self.max_retries} 次后仍失败（网络错误）")
            except Exception:
                # 未知异常或已开始流式后的错误，不重试
                raise

        raise last_exc

    def _calc_delay(self, attempt: int, response_headers: dict) -> float:
        """计算退避延迟，优先用 Retry-After 头"""
        # 优先用服务端的 Retry-After 头
        retry_after = response_headers.get("retry-after") or response_headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), self.max_delay)
            except (ValueError, TypeError):
                pass

        # 指数退避 + 抖动
        import random
        delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
        return min(delay, self.max_delay)
