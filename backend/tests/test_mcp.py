# -*- coding: utf-8 -*-
"""
MCP Server 适配层回归测试

验证：
1. MCP Server 可构建、tools/list 与实际 Agent 注册工具一致且结构合法。
2. tools/call 能执行真实业务工具（query_applications），返回 MCP 规范 result。
3. 未知工具返回 isError。
4. JSON-RPC 路由：initialize / ping / tools/list / tools/call / method-not-found。
"""

import json

import pytest

from app.core.llm.mock_provider import MockProvider
from app.mcp.adapters import OfferCabinMcp, JsonRpcError


@pytest.fixture
def mcp(db_session):
    """构造指向内存库会话的 MCP 适配器（复用 db_session fixture）"""
    def session_factory():
        return db_session
    return OfferCabinMcp(
        user_id="mcp-user",
        session_factory=session_factory,
        provider_factory=lambda: MockProvider(),
    )


EXPECTED_TOOLS = {
    "get_profile", "update_profile", "update_user_preference",
    "create_application", "update_application", "query_applications", "delete_application",
    "get_followups", "search_applications",
    "get_dashboard_stats", "get_timeline_stats", "get_company_stats",
    "extract_job_description", "score_job_match", "generate_resume",
    "generate_cover_letter", "prepare_interview", "get_application_advice",
    "verify_job_authenticity", "evaluate_job",
    "research_company", "generate_interview_questions",
    "evaluate_interview_answer", "review_interview",
    "create_journal_entry", "generate_weekly_summary", "navigate_view",
}


def test_list_tools_complete_and_valid(mcp):
    tools = mcp.list_tools()
    names = {t["name"] for t in tools}
    for name in EXPECTED_TOOLS:
        assert name in names, f"MCP 未暴露工具: {name}"
    # 结构与 Agent 注册表一致（数量相等）
    assert len(tools) == len(EXPECTED_TOOLS)
    for t in tools:
        assert t["name"]
        assert "description" in t
        assert isinstance(t["inputSchema"], dict), f"{t['name']} inputSchema 缺失"


def test_call_tool_query_applications(mcp):
    response = mcp.handle(json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": "query_applications"},
    }))
    body = json.loads(response)
    assert body["id"] == 1
    assert "error" not in body
    result = body["result"]
    assert "content" in result
    assert not result.get("isError", False)
    assert result["content"][0]["type"] == "text"


def test_call_unknown_tool_returns_error(mcp):
    response = mcp.handle(json.dumps({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "no_such_tool", "arguments": {}},
    }))
    body = json.loads(response)
    assert body["result"]["isError"] is True


def test_initialize_handshake(mcp):
    response = mcp.handle(json.dumps({
        "jsonrpc": "2.0", "id": 0,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {}},
    }))
    body = json.loads(response)
    assert body["id"] == 0
    info = body["result"]
    assert info["serverInfo"]["name"] == "offercabin"
    assert info["capabilities"]["tools"] is not None


def test_tools_list_rpc(mcp):
    response = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}))
    body = json.loads(response)
    names = {t["name"] for t in body["result"]["tools"]}
    assert "query_applications" in names


def test_ping(mcp):
    response = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}))
    assert json.loads(response)["result"] == {}


def test_method_not_found(mcp):
    response = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/bogus"}))
    body = json.loads(response)
    assert body["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND


def test_notification_no_response(mcp):
    response = mcp.handle(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
    assert response == ""


def test_parse_error(mcp):
    response = mcp.handle("{not-json")
    body = json.loads(response)
    assert body["error"]["code"] == JsonRpcError.PARSE_ERROR