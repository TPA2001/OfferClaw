"""
LLM 错误分类层次

借鉴 mewcode 的错误分层设计，把 LLM 调用中的异常按可恢复性分类：
- LLMError: 所有 LLM 相关异常的基类
- AuthenticationError: 鉴权失败（API Key 无效/缺失），不可重试
- RateLimitError: 限流，可重试（带 retry_after 提示）
- NetworkError: 网络错误（连接/超时），可重试
- InvalidRequestError: 请求格式错误（参数/schema 不合法），不可重试
- ContentFilterError: 内容审核拦截，不可重试

重试装饰器根据异常类型决定是否重试：
- RateLimitError / NetworkError → 可重试
- AuthenticationError / InvalidRequestError / ContentFilterError → 不可重试
"""

from typing import Optional


class LLMError(Exception):
    """LLM 调用异常基类"""

    def __init__(self, message: str, *, provider: str = "", status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.status_code:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)


class AuthenticationError(LLMError):
    """鉴权失败：API Key 无效/缺失/过期。不可重试。"""


class RateLimitError(LLMError):
    """限流：请求过于频繁或配额耗尽。可重试（等待 retry_after 秒）。"""

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        provider: str = "",
        status_code: Optional[int] = 429,
    ):
        super().__init__(message, provider=provider, status_code=status_code)
        self.retry_after = retry_after


class NetworkError(LLMError):
    """网络错误：连接失败/超时/DNS 解析失败。可重试。"""


class InvalidRequestError(LLMError):
    """请求格式错误：参数不合法/schema 错误/消息格式错误。不可重试。"""


class ContentFilterError(LLMError):
    """内容审核拦截：请求或响应被安全审核拦截。不可重试。"""


# 可重试的异常类型集合（供重试装饰器判断）
RETRYABLE_ERRORS = (RateLimitError, NetworkError)


def is_retryable(err: Exception) -> bool:
    """判断异常是否可重试"""
    return isinstance(err, RETRYABLE_ERRORS)
