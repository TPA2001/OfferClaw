"""
可重试的 LLM Provider 装饰器

对底层 LLMProvider 的 chat / chat_stream 做指数退避重试，
覆盖网络抖动、429 限流、5xx 服务端错误。

优化点（借鉴 mewcode）：
- 使用分类异常（RateLimitError/NetworkError）判断可重试性
- 优先使用 RateLimitError.retry_after 作为退避时间
- 流式调用：仅在建立连接阶段重试，一旦开始输出不再重试

不重试的场景：
- AuthenticationError: 鉴权失败，重试无意义
- InvalidRequestError: 请求格式错误，重试无意义
- ContentFilterError: 内容审核拦截，重试同样会被拒
- 已开始流式输出后的错误（避免重复输出）
"""

import asyncio
import logging
import random
from typing import AsyncIterator, Optional

from .base import LLMProvider, Message, ToolSchema, LLMResponse
from .events import StreamEvent
from .errors import (
    LLMError, RateLimitError, NetworkError,
    is_retryable, RETRYABLE_ERRORS,
)

logger = logging.getLogger("offerclaw.llm.retry")


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
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.inner.chat(messages, tools, temperature, max_tokens)
            except RETRYABLE_ERRORS as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, e)
                    logger.warning(
                        f"LLM 调用可重试错误（{type(e).__name__}），{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LLM 调用重试 {self.max_retries} 次后仍失败（{type(e).__name__}）"
                    )
            except LLMError as e:
                # 不可重试的 LLM 错误，直接抛出
                logger.error(f"LLM 调用失败（不可重试，{type(e).__name__}）: {e.message}")
                raise
            except Exception as e:
                # 未知异常不重试，直接抛出
                logger.error(f"LLM 调用未知异常（不重试）: {type(e).__name__}: {e}")
                raise

        # 重试耗尽，抛出最后一个异常
        raise last_exc  # type: ignore[misc]

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式调用 - 重试仅覆盖建立连接阶段

        一旦开始接收数据 chunk（yielded 过任何事件），不再重试（避免重复输出）。
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                started = False
                async for event in self.inner.chat_stream(messages, tools, temperature, max_tokens):
                    started = True
                    yield event
                # 正常完成，退出重试循环
                return
            except RETRYABLE_ERRORS as e:
                if started:
                    # 已开始流式输出后出错，不重试（避免重复输出）
                    raise
                last_exc = e
                if attempt < self.max_retries:
                    delay = self._calc_delay(attempt, e)
                    logger.warning(
                        f"LLM 流式调用可重试错误（{type(e).__name__}），{delay:.1f}s 后重试 "
                        f"（attempt {attempt + 1}/{self.max_retries}）"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"LLM 流式调用重试 {self.max_retries} 次后仍失败（{type(e).__name__}）"
                    )
            except LLMError as e:
                # 不可重试的 LLM 错误，直接抛出
                logger.error(f"LLM 流式调用失败（不可重试，{type(e).__name__}）: {e.message}")
                raise
            except Exception as e:
                # 未知异常或已开始流式后的错误，不重试
                logger.error(f"LLM 流式调用未知异常（不重试）: {type(e).__name__}: {e}")
                raise

        raise last_exc  # type: ignore[misc]

    def _calc_delay(self, attempt: int, err: Exception) -> float:
        """计算退避延迟

        优先级：
        1. RateLimitError.retry_after（服务端提示的等待时间）
        2. 指数退避 + 抖动
        """
        if isinstance(err, RateLimitError) and err.retry_after is not None:
            return min(err.retry_after, self.max_delay)

        # 指数退避 + 抖动
        delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
        return min(delay, self.max_delay)
