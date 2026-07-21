"""
Agent Runtime - 对应 Pi 的 pi-agent-core 包

核心组件：
- BaseTool: 工具基类
- ToolRegistry: 工具注册中心
- AgentState: 会话状态管理（消息历史、持久化）
- AgentLoop: Agent 循环引擎（感知→思考→工具调用→观察→再思考）
- AgentEvent: 流式输出事件
"""

from .base_tool import BaseTool, ToolResult
from .registry import ToolRegistry
from .state import AgentState
from .events import AgentEvent, ContentDelta, ToolCallStart, ToolResultEvent, DoneEvent, ConfirmRequiredEvent
from .loop import AgentLoop

__all__ = [
    "BaseTool", "ToolResult",
    "ToolRegistry",
    "AgentState",
    "AgentEvent", "ContentDelta", "ToolCallStart", "ToolResultEvent", "DoneEvent", "ConfirmRequiredEvent",
    "AgentLoop",
]
