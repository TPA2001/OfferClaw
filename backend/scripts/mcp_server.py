# -*- coding: utf-8 -*-
"""
OfferCabin MCP Server 入口

把 OfferCabin 的业务工具以 MCP 协议暴露给外部 AI 平台（Claude Desktop 等）。

传输方式：
    --transport stdio  从 stdin 读 JSON-RPC、写回 stdout（默认，面向本地 MCP 客户端）
    --transport sse    以 FastAPI 子应用托管 HTTP+SSE 传输（面向远程/网页客户端）

用法：
    python scripts/mcp_server.py                 # stdio，等同下面两条
    python scripts/mcp_server.py --transport stdio
    python scripts/mcp_server.py --transport sse --host 127.0.0.1 --port 8100
    python scripts/mcp_server.py --list-tools    # 列出将暴露的工具名

环境变量：
    MCP_USER_ID  对外操作的用户 ID（默认 mcp-user）
    TRACE_ENABLED 等复用项目全局配置。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# 允许多 cwd 运行
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.mcp import OfferCabinMcp  # noqa: E402


def build_adapter() -> OfferCabinMcp:
    return OfferCabinMcp(user_id=os.getenv("MCP_USER_ID", "mcp-user"))


def _print_tools(adapter: OfferCabinMcp) -> None:
    names = [t["name"] for t in adapter.list_tools()]
    print(f"共 {len(names)} 个工具已注册:")
    for n in sorted(names):
        print(f"  - {n}")


def _run_stdio(adapter: OfferCabinMcp) -> int:
    from app.mcp.stdio import run_stdio
    return run_stdio(adapter)


def _run_sse(adapter: OfferCabinMcp, host: str, port: int) -> int:
    """以 FastAPI 子应用搭建 HTTP+SSE 传输。

    使用项目已有的 starlette（随 fastapi 锁定版本），避免新依赖。
    MCP HTTP+SSE 会话：客户端先 GET /sse 建立流，再顺序发送 POST /messages?session_id=xxx。
    """
    import uvicorn
    from typing import AsyncIterator
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="OfferCabin MCP", version="0.0.2")

    @app.get("/")
    def index():
        return {
            "service": "offercabin-mcp",
            "endpoints": {"sse": "/sse", "messages": "/messages"},
            "tools": [t["name"] for t in adapter.list_tools()],
        }

    @app.get("/sse")
    async def sse():
        async def event_stream() -> AsyncIterator[str]:
            yield "event: endpoint\ndata: /messages?session_id=sse-offercabin\n\n"
            yield "event: initialized\ndata: {}\n\n"
            # 保持连接，工具调用经 /messages 处理
            import asyncio
            while True:
                await asyncio.sleep(3600)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/messages")
    async def messages(request: Request):
        body = await request.json()
        return _json_response(adapter.handle(json.dumps(body, ensure_ascii=False)))

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _json_response(resp_text: str):
    if not resp_text:
        from fastapi.responses import JSONResponse
        return JSONResponse({"jsonrpc": "2.0", "result": {}, "id": None})
    payload = json.loads(resp_text)
    from fastapi.responses import JSONResponse
    return JSONResponse(payload)


def _main() -> int:
    parser = argparse.ArgumentParser(description="OfferCabin MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--list-tools", action="store_true", help="打印工具清单后退出")
    args = parser.parse_args()

    adapter = build_adapter()
    if args.list_tools:
        _print_tools(adapter)
        return 0

    if args.transport == "stdio":
        return _run_stdio(adapter)
    return _run_sse(adapter, args.host, args.port)


if __name__ == "__main__":
    sys.exit(_main())