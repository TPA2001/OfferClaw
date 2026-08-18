"""
Agent Schema

定义 Agent 对话相关的请求/响应 Pydantic 模型。
"""

from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    """操作确认请求"""
    action_id: str
    approved: bool


class SessionResponse(BaseModel):
    """会话信息"""
    session_id: str
    title: Optional[str] = None
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
