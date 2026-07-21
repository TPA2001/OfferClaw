"""
Agent 状态管理 - 会话历史、持久化
"""

import json
import logging
import uuid
from typing import Optional, Any

from sqlalchemy.orm import Session

from app.core.llm import Message
from app.models.application import AgentSession

logger = logging.getLogger("offerclaw.agent.state")


class AgentState:
    """
    Agent 会话状态

    - 维护消息历史
    - 持久化到 agent_sessions 表
    - 上下文超长时压缩历史
    """

    MAX_MESSAGES = 50                # 消息上限，超过则触发压缩
    COMPRESS_KEEP_RECENT = 20        # 压缩时保留最近 N 条

    def __init__(
        self,
        db: Session,
        user_id: str,
        session_id: Optional[str] = None,
    ):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.messages: list[Message] = []
        self.pending_actions: dict[str, dict[str, Any]] = {}  # action_id → 工具调用信息

        if session_id:
            self._load()

    def _load(self) -> None:
        """从数据库加载会话"""
        try:
            sess = self.db.query(AgentSession).filter(
                AgentSession.id == self.session_id,
                AgentSession.user_id == self.user_id,
            ).first()
            if not sess:
                logger.warning(f"会话 {self.session_id} 不存在，将创建新会话")
                self.session_id = None
                return
            self.messages = [
                Message(**m) for m in json.loads(sess.messages or "[]")
            ]
            logger.info(f"加载会话 {self.session_id}，共 {len(self.messages)} 条消息")
        except Exception as e:
            logger.error(f"加载会话失败: {e}")
            self.session_id = None

    def persist(self) -> str:
        """持久化到数据库，返回 session_id"""
        try:
            messages_json = json.dumps(
                [m.model_dump() for m in self.messages],
                ensure_ascii=False,
                default=str,
            )

            if self.session_id:
                sess = self.db.query(AgentSession).filter(
                    AgentSession.id == self.session_id
                ).first()
                if sess:
                    sess.messages = messages_json
                    if not sess.title and self.messages:
                        first_user = next((m for m in self.messages if m.role == "user"), None)
                        if first_user and first_user.content:
                            sess.title = first_user.content[:50]
            else:
                sess = AgentSession(
                    id=str(uuid.uuid4()),
                    user_id=self.user_id,
                    messages=messages_json,
                )
                if self.messages:
                    first_user = next((m for m in self.messages if m.role == "user"), None)
                    if first_user and first_user.content:
                        sess.title = first_user.content[:50]
                self.db.add(sess)
                self.db.flush()  # 让 id 生效
                self.session_id = str(sess.id)

            self.db.commit()
            return self.session_id
        except Exception as e:
            logger.error(f"持久化会话失败: {e}")
            self.db.rollback()
            return self.session_id or ""

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        if len(self.messages) > self.MAX_MESSAGES:
            self.compress()

    def add_user(self, content: str) -> None:
        self.add_message(Message(role="user", content=content))

    def add_assistant(self, content: Optional[str] = None, tool_calls: Optional[list] = None) -> None:
        from app.core.llm import ToolCall
        self.add_message(Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or [],
        ))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.add_message(Message(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        ))

    def compress(self) -> None:
        """压缩历史 - 保留 system + 最近 N 条，旧消息汇总"""
        if len(self.messages) <= self.MAX_MESSAGES:
            return

        system_msgs = [m for m in self.messages if m.role == "system"]
        recent = self.messages[-self.COMPRESS_KEEP_RECENT:]

        # 旧消息汇总（简化版：直接丢弃，保留 system + 最近）
        old_count = len(self.messages) - len(system_msgs) - len(recent)
        summary = Message(
            role="system",
            content=f"[历史压缩] 之前 {old_count} 条对话已省略，保留最近 {len(recent)} 条。",
        )

        self.messages = system_msgs + [summary] + recent
        logger.info(f"压缩历史：{old_count + len(self.messages)} → {len(self.messages)}")

    def to_messages(self) -> list[Message]:
        """返回传给 LLM 的消息列表（不含 system，system 单独传）"""
        return [m for m in self.messages if m.role != "system"]

    def register_pending_action(self, action_id: str, info: dict) -> None:
        self.pending_actions[action_id] = info

    def resolve_pending_action(self, action_id: str) -> Optional[dict]:
        return self.pending_actions.pop(action_id, None)
