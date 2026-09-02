"""
MCP 应用包：把 OfferCabin 业务能力以 MCP 协议对外暴露。

模块结构：
- adapters.py: OfferCabinMcp —— 工具适配 + JSON-RPC 请求路由（可单测）
- stdio.py: run_stdio —— stdio 传输主循环（供 `scripts/mcp_server.py` 使用）
"""

from .adapters import (
    OfferCabinMcp,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
)

__all__ = [
    "OfferCabinMcp",
    "PROTOCOL_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
]