"""
Agent 流式事件
"""

from typing import Any, Optional
from pydantic import BaseModel

from app.core.llm import ToolCall, TokenUsage


class AgentEvent(BaseModel):
    """Agent 事件基类"""
    type: str


class ContentDelta(AgentEvent):
    """文本增量"""
    type: str = "content_delta"
    delta: str = ""


class ToolCallStart(AgentEvent):
    """工具调用开始"""
    type: str = "tool_call_start"
    tool_call: ToolCall


class ToolResultEvent(AgentEvent):
    """工具执行结果"""
    type: str = "tool_result"
    tool_call_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class ConfirmRequiredEvent(AgentEvent):
    """需要用户确认"""
    type: str = "confirm_required"
    action_id: str
    tool_name: str
    description: str
    arguments: dict


class DoneEvent(AgentEvent):
    """完成事件"""
    type: str = "done"
    session_id: str
    usage: Optional[TokenUsage] = None
    finish_reason: str = "stop"


class NavigateEvent(AgentEvent):
    """前端页面跳转事件 — Agent 请求切换到某个功能视图"""
    type: str = "navigate"
    target: str                # 路由路径：/kanban, /profile, /jobs, /smart-fill, /interview, /settings
    params: dict = {}          # 可选的查询参数
    message: str = ""          # 给用户的说明


class ErrorEvent(AgentEvent):
    """错误事件"""
    type: str = "error"
    message: str
