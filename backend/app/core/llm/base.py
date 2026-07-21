"""
LLM Provider 基础抽象与数据结构
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token 使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


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
        """转换为 provider 需要的 dict 格式（去掉空字段）"""
        d = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
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
    """LLM Provider 抽象接口"""

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
    ):
        """
        流式输出接口 - 默认实现为非流式，子类可覆盖

        Yields:
            dict: {"type": "content"|"tool_call"|"done", ...}
        """
        resp = await self.chat(messages, tools, temperature, max_tokens)
        if resp.content:
            yield {"type": "content", "delta": resp.content}
        for tc in resp.tool_calls:
            yield {"type": "tool_call", "tool_call": tc}
        yield {"type": "done", "usage": resp.usage}
