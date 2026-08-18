"""
LLM Provider 基础抽象与数据结构

核心抽象：
- LLMProvider: Provider 接口（chat + chat_stream）
- Message / ToolCall / ToolSchema: 标准化数据结构
- LLMResponse: 统一响应格式
- TokenUsage: Token 使用统计（含 cache 命中数）

设计要点（借鉴 mewcode）：
- chat_stream 返回类型化 StreamEvent（dataclass），而非 dict
- TokenUsage 支持 cache_read / cache_creation（prompt cache 统计）
- Message.to_dict() 保持向后兼容，但 provider 应优先使用 serialization 模块
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

from .events import StreamEvent


class TokenUsage(BaseModel):
    """Token 使用统计

    字段含义（与 Anthropic/OpenAI 对齐）：
    - prompt_tokens: 实际计费的输入 token（已排除 cache 命中的部分）
    - completion_tokens: 输出 token
    - total_tokens: prompt + completion
    - cache_read: prompt cache 命中的 token 数（按 10% 计费）
    - cache_creation: prompt cache 写入的 token 数（首次缓存的开销）

    实际 prompt 大小 = prompt_tokens + cache_read + cache_creation
    （OpenAI 系列只暴露 cache_read，cache_creation 始终为 0）
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0

    def add_output(self, output_tokens: int) -> None:
        """累加输出 token 并更新 total"""
        self.completion_tokens += output_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens


class ToolCall(BaseModel):
    """标准化的工具调用请求"""
    id: str                                  # 调用 ID（用于关联 tool 结果）
    name: str                                # 工具名
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """工具定义（OpenAI function calling 格式）"""
    name: str
    description: str
    parameters: dict[str, Any]               # JSON Schema


class Message(BaseModel):
    """统一的消息结构"""
    role: str                                # system / user / assistant / tool
    content: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: Optional[str] = None       # role=tool 时关联的 tool_call.id
    name: Optional[str] = None               # role=tool 时工具名

    def to_dict(self) -> dict:
        """转换为 OpenAI Chat Completions 格式（去掉空字段）

        注意：provider 应优先使用 serialization.build_chat_completion_messages()
        来处理批量消息转换，此方法仅用于简单场景和向后兼容。
        """
        d = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            import json
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        if isinstance(tc.arguments, dict)
                        else str(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


class LLMResponse(BaseModel):
    """LLM 统一响应"""
    content: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    usage: TokenUsage = Field(default_factory=TokenUsage)


class LLMProvider(ABC):
    """LLM Provider 抽象接口

    子类需实现：
    - chat(): 同步返回完整响应
    - chat_stream(): 流式返回 StreamEvent 序列

    chat_stream 的默认实现基于 chat()，子类应覆盖以获得真正的流式体验。
    """

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        同步返回完整响应的 chat 接口

        Args:
            messages: 对话历史
            tools: 可调用的工具定义
            temperature: 采样温度
            max_tokens: 最大输出 token
        """
        ...

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        流式输出接口 - 默认实现为非流式，子类应覆盖

        Yields:
            StreamEvent: TextDelta / ReasoningDelta / ReasoningComplete /
                         ToolCallStart / ToolCallDelta / ToolCallComplete / StreamEnd
        """
        from .events import TextDelta, ToolCallStart, ToolCallComplete, StreamEnd

        resp = await self.chat(messages, tools, temperature, max_tokens)
        if resp.content:
            yield TextDelta(text=resp.content)
        for tc in resp.tool_calls:
            yield ToolCallStart(tool_name=tc.name, tool_id=tc.id)
            yield ToolCallComplete(tool_id=tc.id, tool_name=tc.name, arguments=tc.arguments)
        yield StreamEnd(
            finish_reason=resp.finish_reason,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            cache_read=resp.usage.cache_read,
            cache_creation=resp.usage.cache_creation,
        )
