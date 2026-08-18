"""
轻量速率限制器（内存滑动窗口）

针对高成本端点（Agent 对话、Boss 搜索、自动填表）做限流，
防止滥用导致 LLM 成本失控或被目标站点封 IP。

策略：
- 基于 IP + 路径的滑动窗口计数
- 内存存储（单实例部署足够；多实例需换 Redis 后端）
- 超限返回 429 Too Many Requests

使用方式（FastAPI 依赖注入）：
    from app.core.rate_limit import rate_limit

    @router.post("/chat", dependencies=[Depends(rate_limit(limit=20, window=60))])
    async def chat(...): ...
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from fastapi import Depends, Request
from app.core.response import RateLimitError


class _SlidingWindow:
    """线程安全的滑动窗口计数器"""

    def __init__(self):
        self._lock = Lock()
        # key = "ip:path", value = deque[timestamps]
        self._buckets: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """记录一次请求，返回 (是否允许, 剩余配额, 重置秒数)"""
        now = time.time()
        cutoff = now - window

        with self._lock:
            bucket = self._buckets[key]
            # 清除过期记录
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                # 计算最早记录何时过期
                reset = int(bucket[0] + window - now) + 1
                return False, 0, max(reset, 1)

            bucket.append(now)
            remaining = limit - len(bucket)
            return True, remaining, window


# 全局单例
_counter = _SlidingWindow()


def rate_limit(limit: int = 20, window: int = 60):
    """速率限制依赖工厂

    Args:
        limit: 窗口内允许的最大请求数
        window: 窗口大小（秒）
    """
    def _check(request: Request):
        # 提取客户端 IP（优先 X-Forwarded-For，兼容反代）
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        key = f"{client_ip}:{request.url.path}"
        allowed, remaining, reset = _counter.hit(key, limit, window)

        if not allowed:
            raise RateLimitError(
                f"请求过于频繁，请 {reset} 秒后重试",
                headers={"Retry-After": str(reset)},
            )

    return _check


# 预设的限流策略
agent_rate_limit = rate_limit(limit=20, window=60)      # Agent 对话：20 次/分钟
automation_rate_limit = rate_limit(limit=10, window=60)  # 自动化（Boss搜索/填表）：10 次/分钟
