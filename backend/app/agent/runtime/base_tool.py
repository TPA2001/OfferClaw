"""
工具基类
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.llm import ToolSchema


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    requires_confirmation: bool = False       # 是否需要用户二次确认（敏感操作）
    pending_action_id: Optional[str] = None   # 待确认操作的 ID

    def to_message_content(self) -> str:
        """转换为 tool 消息的 content 字符串"""
        import json
        if not self.success:
            return f"工具执行失败: {self.error}"
        if self.requires_confirmation:
            return f"操作待确认（action_id={self.pending_action_id}）"
        try:
            return json.dumps(self.data, ensure_ascii=False, default=str)
        except Exception:
            return str(self.data)


class BaseTool(ABC):
    """工具基类 - 所有 agent 工具继承此类"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}            # JSON Schema
    requires_confirmation: bool = False        # 是否需要用户确认

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回 ToolResult"""
        ...

    def to_schema(self) -> ToolSchema:
        """转换为 LLM 工具定义"""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def arun(self, **kwargs) -> ToolResult:
        """统一入口，包装异常"""
        try:
            return await self.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
