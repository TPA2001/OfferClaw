"""
MCP（Model Context Protocol）服务端适配层

把 OfferCabin 的 Agent 业务工具批量暴露为 MCP 工具，供外部 AI 平台
（Claude Desktop / Cursor 等支持 MCP 的客户端）通过 stdio 或 HTTP+SSE 调用。

为什么零依赖手写：
- 官方 mcp SDK 强依赖 pydantic>=2.10 / 新版 starlette，与项目锁定的
  fastapi 0.111（要求 starlette<0.38）冲突，会破坏生产依赖栈。
- 本项目工具本身已用 JSON Schema 描述参数（BaseTool.parameters），
  直接按 MCP 规范回填 inputSchema 即可，无需额外类型内省。

协议对齐：MCP 2024-11-05（tools/list + tools/call）。JSON-RPC 2.0 封装在
stdio.py / 外部传输中完成；本模块只关注「工具适配 + 协议数据生成」，可独立单测。

用例如下（JSON-RPC 请求 → 响应）：
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
    {"jsonrpc":"2.0","id":2,"method":"tools/list"}
    {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"query_applications"}}
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from app.core.database import SessionLocal
from app.core.llm import get_default_provider
from app.agent.apps import build_tool_registry

logger = logging.getLogger("offercabin.mcp")

# MCP 协议版本（最新稳定版）
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "offercabin"
SERVER_VERSION = "0.0.2"

# 未指定用户时的默认 MCP 操作对象（外部平台无法方便携带 OfferCabin JWT）
DEFAULT_USER_ID = os.getenv("MCP_USER_ID", "mcp-user").strip() or "mcp-user"

# JSON-RPC 错误码
class JsonRpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


def _text_content(text: str) -> dict[str, Any]:
    """构造 MCP text content 切片"""
    return {"type": "text", "text": text}


class OfferCabinMcp:
    """把 OfferCabin 业务工具适配成 MCP 工具

    每次 tools/list 或 tools/call 都新建独立 DB 会话 + 工具注册表，
    无状态、可并发，避免长连接独占 session（与 Agent SSE 同样的思路）。
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        session_factory: Optional[Callable[..., Any]] = None,
        provider_factory: Optional[Callable[..., Any]] = None,
    ):
        self.user_id = user_id or DEFAULT_USER_ID
        self.session_factory = session_factory or SessionLocal
        # provider_factory 必须返回可调用（同步），内部懒获取一次
        self.provider_factory = provider_factory or get_default_provider

    # ---------- 工具适配 ----------

    def list_tools(self) -> list[dict[str, Any]]:
        """返回 MCP tools/list 所需的工具列表（name/description/inputSchema）"""
        db = self.session_factory()
        try:
            registry = build_tool_registry(self.provider_factory(), db, self.user_id)
            return [
                {
                    "name": s.name,
                    "description": s.description,
                    "inputSchema": s.parameters,
                }
                for s in registry.schemas()
            ]
        finally:
            self._close(db)

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]]) -> dict[str, Any]:
        """执行工具，返回 MCP tools/call 的 result（content + isError）"""
        db = self.session_factory()
        try:
            registry = build_tool_registry(self.provider_factory(), db, self.user_id)
            tool = registry.get(name)
            if tool is None:
                return {
                    "content": [_text_content(f"工具不存在: {name}")],
                    "isError": True,
                }
            result = await tool.arun(**(arguments or {}))
            text = result.to_message_content()
            if result.requires_confirmation:
                return {
                    "content": [_text_content(
                        "该操作需要人工确认，MCP 环境下无法二次确认，已挂起。"
                        f" action_id={result.pending_action_id}")]
                }
            return {
                "content": [_text_content(text)],
                "isError": not result.success,
            }
        except Exception as e:  # noqa: BLE001
            logger.exception(f"MCP call_tool({name}) 异常")
            return {"content": [_text_content(f"工具执行异常: {type(e).__name__}: {e}")], "isError": True}
        finally:
            self._close(db)

    def _close(self, db: Any) -> None:
        try:
            db.close()
        except Exception:
            pass

    # ---------- JSON-RPC 请求路由（供 stdio/SSE 传输复用，也可单测） ----------

    def handle(self, message: str) -> str:
        """处理单个 JSON-RPC 消息（字符串），返回要写出的响应（可能为空串=通知）"""
        try:
            request = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": JsonRpcError.PARSE_ERROR, "message": "Parse error"},
            }, ensure_ascii=False)

        if not isinstance(request, dict):
            return json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": JsonRpcError.INVALID_REQUEST, "message": "Invalid Request"},
            }, ensure_ascii=False)

        rpc_id = request.get("id")
        method = request.get("method", "")

        # 通知类：无 id，不回应
        if rpc_id is None and method in ("notifications/initialized", "notifications/cancelled"):
            return ""

        try:
            result, error = self._dispatch(method, request.get("params") or {})
        except Exception as e:  # noqa: BLE001
            logger.exception(f"MCP 处理 {method} 异常")
            error = {"code": JsonRpcError.INTERNAL_ERROR, "message": f"Internal error: {e}"}
            result = None

        response: dict[str, Any] = {"jsonrpc": "2.0", "result": result, "id": rpc_id}
        if error is not None:
            response.pop("result", None)
            response["error"] = error
        return json.dumps(response, ensure_ascii=False)

    def _dispatch(self, method: str, params: dict[str, Any]) -> tuple[Any, Any]:
        """同步分发；tools/call 内部进行同步封装（本模块保持同步回调语义）"""
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }, None

        if method == "ping":
            return {}, None

        if method == "tools/list":
            return {"tools": self.list_tools()}, None

        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            # call_tool 是 async，这里用 asyncio.run 同步等待
            import asyncio
            return asyncio.run(self.call_tool(name, arguments)), None

        return None, {"code": JsonRpcError.METHOD_NOT_FOUND, "message": f"Method not found: {method}"}