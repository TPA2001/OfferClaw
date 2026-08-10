"""
LLM 抽象层 - 对应 Pi 的 pi-ai 包
统一多 provider 接口，屏蔽 OpenAI/Anthropic/Qwen 差异

核心抽象：
- LLMProvider: Provider 接口
- Message / ToolCall / ToolSchema: 标准化数据结构
- LLMResponse: 统一响应格式
- RetriableLLMProvider: 带指数退避重试的装饰器
"""

from .base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolSchema,
    LLMResponse,
    TokenUsage,
)
from .factory import create_provider, get_default_provider
from .openai_provider import OpenAIProvider
from .mock_provider import MockProvider
from .retry_provider import RetriableLLMProvider

__all__ = [
    "LLMProvider",
    "Message",
    "ToolCall",
    "ToolSchema",
    "LLMResponse",
    "TokenUsage",
    "create_provider",
    "get_default_provider",
    "OpenAIProvider",
    "MockProvider",
    "RetriableLLMProvider",
]
