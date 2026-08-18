"""
LLM 流式事件类型定义

借鉴 mewcode 的流式事件设计，用 dataclass 替代 dict，提供类型安全的事件流。

事件类型：
- TextDelta: 文本内容增量
- ReasoningDelta: 推理过程增量（DeepSeek reasoning_content / Claude thinking）
- ReasoningComplete: 推理过程完成
- ToolCallStart: 工具调用开始（带 tool name + id）
- ToolCallDelta: 工具调用参数增量（JSON 字符串片段）
- ToolCallComplete: 工具调用完成（带完整 arguments dict）
- StreamEnd: 流结束（带 token 用量统计 + finish_reason）

设计要点：
- 不依赖 base.py，避免循环导入（base.py 导入本模块的 StreamEvent）
- StreamEnd 直接用 int 字段记录 token 用量，由 provider 负责构造 TokenUsage
- ToolCallComplete 直接用 dict 存 arguments，由消费方转成 ToolCall

事件流时序示例：
    TextDelta("你好") → TextDelta("，") → ToolCallStart("search_jobs", "call_123")
    → ToolCallDelta('{"key') → ToolCallDelta('word":"Java"}')
    → ToolCallComplete("call_123", "search_jobs", {"keyword":"Java"})
    → StreamEnd(input_tokens=100, output_tokens=20, finish_reason="tool_calls")
"""

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class TextDelta:
    """文本内容增量"""
    text: str


@dataclass
class ReasoningDelta:
    """推理过程增量（DeepSeek reasoning_content / OpenAI o1 reasoning）"""
    text: str


@dataclass
class ReasoningComplete:
    """推理过程完成"""
    reasoning: str
    signature: str = ""  # Claude thinking 的签名（OpenAI 系列为空）


@dataclass
class ToolCallStart:
    """工具调用开始"""
    tool_name: str
    tool_id: str


@dataclass
class ToolCallDelta:
    """工具调用参数增量（JSON 字符串片段）"""
    text: str


@dataclass
class ToolCallComplete:
    """工具调用完成"""
    tool_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEnd:
    """流结束

    token 用量字段含义（与 Anthropic/OpenAI 对齐）：
    - input_tokens: 实际计费的输入 token（已排除 cache 命中的部分）
    - output_tokens: 输出 token
    - cache_read: prompt cache 命中的 token 数（按 10% 计费）
    - cache_creation: prompt cache 写入的 token 数（首次缓存的开销）

    实际 prompt 大小 = input_tokens + cache_read + cache_creation
    （OpenAI 系列只暴露 cache_read，cache_creation 始终为 0）
    """
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0


# 流式事件联合类型
StreamEvent = Union[
    TextDelta,
    ReasoningDelta,
    ReasoningComplete,
    ToolCallStart,
    ToolCallDelta,
    ToolCallComplete,
    StreamEnd,
]
