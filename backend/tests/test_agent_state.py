"""
Agent 状态管理与压缩逻辑测试

覆盖：
- AgentState 消息增删
- 历史压缩触发与保留策略
- 会话标题生成
- pending_actions 管理
"""
import pytest

from app.core.llm import Message


class TestAgentStateMessages:
    """AgentState 消息管理测试"""

    def test_add_user_message(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        state.add_user("你好")

        # add_user 直接增加一条 user 消息
        assert len(state.messages) == 1
        assert state.messages[-1].role == "user"
        assert state.messages[-1].content == "你好"

    def test_add_user_message_with_system(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        state.messages.append(Message(role="system", content="system prompt"))
        state.add_user("你好")
        assert len(state.messages) == 2
        assert state.messages[-1].role == "user"

    def test_add_tool_result(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        state.add_tool_result(
            tool_call_id="call_001",
            name="query_applications",
            content='{"message":"共 3 条记录"}',
        )

        assert len(state.messages) == 1
        msg = state.messages[0]
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_001"
        assert msg.name == "query_applications"


class TestAgentStateCompression:
    """历史压缩逻辑测试"""

    def test_compress_keeps_recent(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        # 直接 append（绕过 add_message 的自动压缩），构造超过 MAX_MESSAGES 的历史
        state.messages.append(Message(role="system", content="system"))
        for i in range(60):
            state.messages.append(Message(role="user", content=f"消息 {i}"))

        assert len(state.messages) == 61  # 1 system + 60 user

        # 手动触发一次压缩
        state.compress()

        # 应保留 system + 压缩摘要 + 最近 COMPRESS_KEEP_RECENT=20 条 = 22
        assert len(state.messages) == 22
        # system 在最前
        assert state.messages[0].role == "system"
        assert state.messages[0].content == "system"
        # 第二条是压缩摘要
        assert state.messages[1].role == "system"
        assert "历史压缩" in state.messages[1].content
        # 最后一条是最近的消息
        assert state.messages[-1].content == "消息 59"

    def test_compress_not_triggered_below_threshold(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        state.messages.append(Message(role="system", content="system"))
        for i in range(10):
            state.add_user(f"消息 {i}")

        original_len = len(state.messages)
        state.compress()

        # 低于阈值不应压缩
        assert len(state.messages) == original_len


class TestTitleGeneration:
    """会话标题生成测试"""

    def test_short_input_as_title(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        title = state._generate_title("查看投递")
        assert title == "查看投递"

    def test_long_input_truncated(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        long_text = "帮我分析一下腾讯后端开发岗位的匹配度并生成简历"
        title = state._generate_title(long_text)
        assert title is not None
        assert len(title) <= 15

    def test_empty_input_returns_none(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        assert state._generate_title("") is None
        assert state._generate_title(None) is None


class TestPendingActions:
    """pending_actions 管理测试"""

    def test_register_and_resolve(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        state.register_pending_action("action_001", {
            "tool_name": "delete_application",
            "arguments": {"application_id": "app-001"},
        })

        info = state.resolve_pending_action("action_001")
        assert info is not None
        assert info["tool_name"] == "delete_application"

        # 二次 resolve 应返回 None（已弹出）
        assert state.resolve_pending_action("action_001") is None

    def test_resolve_nonexistent(self, db_session):
        from app.agent.runtime.state import AgentState

        state = AgentState(db=db_session, user_id="test-user")
        assert state.resolve_pending_action("nonexistent") is None
