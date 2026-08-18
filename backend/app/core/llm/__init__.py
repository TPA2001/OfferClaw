"""
LLM 抽象层 - 对应 Pi 的 pi-ai 包
统一多 provider 接口，屏蔽 OpenAI/Anthropic/Qwen 差异

核心抽象：
- LLMProvider: Provider 接口（chat + chat_stream）
- Message / ToolCall / ToolSchema: 标准化数据结构
- LLMResponse: 统一响应格式
- TokenUsage: Token 使用统计（含 cache 命中数）
- StreamEvent: 流式事件类型（TextDelta/ToolCallStart/.../StreamEnd）
- LLMError 层次: 分类异常（Auth/RateLimit/Network/InvalidRequest/ContentFilter）

模块结构（借鉴 mewcode）：
- base.py: Provider 接口 + 数据结构
- events.py: 流式事件类型定义
- serialization.py: 消息序列化层（Message → provider 格式）
- errors.py: LLM 错误分类层次
- openai_provider.py: OpenAI 兼容协议 Provider
- mock_provider.py: Mock 降级 Provider
- retry_provider.py: 指数退避重试装饰器
- factory.py: Provider 工厂（模型分级：agent/gen）
"""

from .base import (
    LLMProvider,
    Message,
    ToolCall,
    ToolSchema,
    LLMResponse,
    TokenUsage,
)
from .events import (
    StreamEvent,
    TextDelta,
    ReasoningDelta,
    ReasoningComplete,
    ToolCallStart,
    ToolCallDelta,
    ToolCallComplete,
    StreamEnd,
)
from .errors import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    InvalidRequestError,
    ContentFilterError,
    is_retryable,
)
from .serialization import (
    build_chat_completion_messages,
    build_tools_for_chat_completion,
    parse_tool_call_arguments,
)
from .factory import (
    create_provider,
    get_default_provider,
    get_agent_provider,
    get_gen_provider,
    reload_llm_config,
    mask_key,
)
from .openai_provider import OpenAIProvider
from .mock_provider import MockProvider
from .retry_provider import RetriableLLMProvider

__all__ = [
    # 数据结构
    "LLMProvider",
    "Message",
    "ToolCall",
    "ToolSchema",
    "LLMResponse",
    "TokenUsage",
    # 流式事件
    "StreamEvent",
    "TextDelta",
    "ReasoningDelta",
    "ReasoningComplete",
    "ToolCallStart",
    "ToolCallDelta",
    "ToolCallComplete",
    "StreamEnd",
    # 错误分类
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "NetworkError",
    "InvalidRequestError",
    "ContentFilterError",
    "is_retryable",
    # 序列化
    "build_chat_completion_messages",
    "build_tools_for_chat_completion",
    "parse_tool_call_arguments",
    # Provider 工厂
    "create_provider",
    "get_default_provider",
    "get_agent_provider",
    "get_gen_provider",
    "reload_llm_config",
    "mask_key",
    # Provider 实现
    "OpenAIProvider",
    "MockProvider",
    "RetriableLLMProvider",
]
