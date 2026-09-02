"""
MCP stdio 传输主循环

MCP 标准 stdio 传输：每行一条 JSON-RPC 消息（compact JSON），
服务器从 stdin 读取、把响应写到 stdout。空行忽略。

供 `scripts/mcp_server.py --transport stdio` 使用。
"""

from __future__ import annotations

import sys
import logging
from typing import Optional

from .adapters import OfferCabinMcp

logger = logging.getLogger("offercabin.mcp.stdio")


def run_stdio(
    adapter: Optional[OfferCabinMcp] = None,
    *,
    max_requests: Optional[int] = None,
) -> int:
    """运行 stdio 主循环，返回退出码（正常=0）。

    adapter 为 None 时自动创建缺省 OfferCabinMcp（懒构建，避免无关导入链）。
    max_requests：有界运行（测试用）；None 表示运行到 stdin 关闭。
    """
    a = adapter or OfferCabinMcp()
    handled = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = a.handle(line)
        if response:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
        handled += 1
        if max_requests is not None and handled >= max_requests:
            break
    return 0