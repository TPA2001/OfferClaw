"""
长期记忆工具：允许 Agent 主动写入/修正用户偏好

当 Agent 在对话中发现用户明确表达了一个想长期记住的偏好
（想去的公司、目标城市、薪资期望、职业方向、时间偏好等）时，
调用 update_user_preference 落库，跨会话保持认知一致。
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..runtime.base_tool import BaseTool, ToolResult
from ..memory import store
from ..memory.embedding import get_embedder


class UpdateUserPreferenceTool(BaseTool):
    """主动记录/修正用户的长期偏好记忆"""

    name = "update_user_preference"
    description = (
        "记录或修正用户的长期偏好，供后续所有会话长期记住（如想去的公司、目标城市、"
        "薪资期望、职业方向、工作节奏等）。当用户明确告知一个希望长期记住的偏好时调用。"
        "memory_type 一般用 preference，重大经历/反馈可用 experience/feedback。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要牢记的具体偏好内容，如'用户期望去杭州的互联网中厂，薪资不低于25k'",
            },
            "memory_type": {
                "type": "string",
                "enum": ["preference", "experience", "feedback"],
                "description": "记忆类型，默认 preference",
            },
        },
        "required": ["content"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        content: str,
        memory_type: str = "preference",
    ) -> ToolResult:
        content = (content or "").strip()
        if not content:
            return ToolResult(success=False, error="content 不能为空")

        vec = get_embedder().embed(content)
        store.create_memory(
            self.db,
            user_id=self.user_id,
            memory_type=memory_type,
            content=content,
            embedding=json.dumps(vec),
            metadata={"source": "agent"},
            source="agent",
        )
        return ToolResult(success=True, data={
            "message": f"已记住你的偏好：{content[:60]}",
            "memory_type": memory_type,
        })