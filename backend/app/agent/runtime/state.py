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

logger = logging.getLogger("offercabin.agent.state")

# 进程级待确认操作注册表：action_id → 工具调用信息
# 原因：/chat 与 /confirm 是两次独立 HTTP 请求，各自新建 AgentState（内存态不共享）。
# 挂起的确认操作必须跨请求保留，否则 confirm 时 resolve 必然返回 None、确认流程整体失效。
# 按全局唯一 action_id 索引（uuid 生成），不依赖 session_id（首次对话时 session_id 可能尚为 None）。
# 进程重启后注册表清空，此时再 confirm 会提示"无效的 action_id"，可接受。
_PENDING_REGISTRY: dict[str, dict[str, Any]] = {}


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

            # 提取首条用户消息用于标题生成
            first_user_msg = next(
                (m for m in self.messages if m.role == "user" and m.content),
                None,
            )

            if self.session_id:
                sess = self.db.query(AgentSession).filter(
                    AgentSession.id == self.session_id
                ).first()
                if sess:
                    sess.messages = messages_json
                    # 仅在标题仍是默认值（未命名/截断）时尝试智能生成
                    if (not sess.title or sess.title == "未命名会话") and first_user_msg:
                        title = self._generate_title(first_user_msg.content)
                        if title:
                            sess.title = title
            else:
                title = None
                if first_user_msg:
                    title = self._generate_title(first_user_msg.content)
                sess = AgentSession(
                    id=str(uuid.uuid4()),
                    user_id=self.user_id,
                    messages=messages_json,
                    title=title or (first_user_msg.content[:50] if first_user_msg and first_user_msg.content else "未命名会话"),
                )
                self.db.add(sess)
                self.db.flush()  # 让 id 生效
                self.session_id = str(sess.id)

            self.db.commit()
            return self.session_id
        except Exception as e:
            logger.error(f"持久化会话失败: {e}")
            self.db.rollback()
            return self.session_id or ""

    def _generate_title(self, user_input: str) -> Optional[str]:
        """从用户输入生成简短标题（4-10 字）。

        采用规则化提取而非 LLM 调用，原因：
        1. persist() 是同步方法，无法直接 await async LLM
        2. 标题生成是低频操作，规则提取已足够好
        3. 避免 LLM 不可用时会话持久化失败
        """
        text = (user_input or "").strip()
        if not text:
            return None

        # 极短输入直接用原文
        if len(text) <= 12:
            return text

        # 规则化提取：取前 10 个字符，在最后一个完整语义边界截断
        # 优先在标点/空格处截断，避免半句话
        import re
        snippet = text[:15]
        # 找最后一个标点或空格
        m = list(re.finditer(r'[，。！？\s,\.!?;；]', snippet))
        if m:
            cut = m[-1].start()
            if cut >= 4:  # 至少保留 4 字
                return text[:cut]
        return text[:10]

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
        # 同时写入进程级注册表，供跨请求的 confirm 端点恢复
        _PENDING_REGISTRY[action_id] = info

    def resolve_pending_action(self, action_id: str) -> Optional[dict]:
        # 先查实例内存（同实例复用场景），再查进程级注册表（跨请求场景）
        info = self.pending_actions.pop(action_id, None)
        if info is not None:
            # 同实例命中也要同步清理进程级注册表，避免同一 action 被二次弹出
            _PENDING_REGISTRY.pop(action_id, None)
            return info
        return _PENDING_REGISTRY.pop(action_id, None)
