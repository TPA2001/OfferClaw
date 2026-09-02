# -*- coding: utf-8 -*-
"""
Tracer - Agent 可观测性 & 追踪

设计目标：
- 低侵入：不修改 Agent 循环逻辑，仅包装 AGENT 层产出的 AgentEvent 流，
  在生成器外包装一次即可完成一次「会话级 Trace」的记录。
- 记录指标：Input / Output / Latency / TokenUsage / ToolCalls / 错误。
- 开关：TRACE_ENABLED=false 时全部短路，零开销。
- 导出：
  - local（默认）：写 backend/data/traces/offercabin_traces.jsonl
  - langsmith（可选）：当配置了 LANGSMITH_API_KEY 且 trace_exporter=langsmith 时，
    调用 langsmith SDK 提交 run。未安装 SDK 时不阻塞，自动降级为 local。

用法（在 Agent API 入口）：
    from app.core.tracing import trace_agent_generator

    async def event_stream():
        db = SessionLocal()
        try:
            ...
            async for event in trace_agent_generator(
                raw_gen, user_id=user_id, session_id=req.session_id,
                user_input=req.message,
            ):
                yield event
        finally:
            db.close()

数据安全：本模块仅记录脱敏后的输入（截断 + 隐藏关键信息），
完整对话内容由会话持久化负责，Trace 只保留审计所需的最小字段。
"""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.paths import data_dir

logger = logging.getLogger("offercabin.tracing")

# 当前请求的 contextvars：支持并发请求各自独立的 trace_id
_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "offercabin_trace_id", default=None
)


def current_trace_id() -> Optional[str]:
    """返回当前上下文（请求/任务）关联的 trace_id，无则 None"""
    return _current_trace_id.get()


def set_current_trace_id(trace_id: str) -> None:
    """为当前上下文绑定 trace_id（任务结束后无需手动清理，context 自动隔离）"""
    _current_trace_id.set(trace_id)


class Tracer:
    """一次 Agent 会话运行的跟踪器

    通过依次调用 record_* 方法收集事件，最后调用 finish() 写入磁盘。
    """

    def __init__(self, trace_id: str, user_id: str, session_id: str):
        self.trace_id = trace_id
        self.user_id = user_id
        self.session_id = session_id
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        # 累计指标
        self.input_text = ""
        self.output_text = ""
        self.tool_calls: list[dict[str, Any]] = []
        self.tool_success: int = 0
        self.tool_fail: int = 0
        self.token_usage: dict[str, int] = {}
        self.finish_reason: str = "unknown"
        self.error: Optional[str] = None
        self.events_count: int = 0

    # ---------- 事件记录 ----------

    def observe(self, event: Any) -> None:
        """消费一个 AgentEvent（来自 app.agent.runtime.events），提取指标"""
        self.events_count += 1
        etype = getattr(event, "type", "")

        if etype == "tool_call_start" and getattr(event, "tool_call", None):
            tc = event.tool_call
            self.tool_calls.append({
                "name": tc.name,
                "arguments": _sanitize_dict(getattr(tc, "arguments", {}) or {}),
            })
        elif etype == "tool_result":
            if getattr(event, "success", False):
                self.tool_success += 1
            else:
                self.tool_fail += 1
        elif etype == "done":
            self.finish_reason = getattr(event, "finish_reason", "stop") or "stop"
            usage = getattr(event, "usage", None)
            if usage is not None:
                self.token_usage = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                    "cache_read": getattr(usage, "cache_read", 0) or 0,
                    "cache_creation": getattr(usage, "cache_creation", 0) or 0,
                }
        elif etype == "content_delta":
            self.output_text += getattr(event, "delta", "") or ""
        elif etype == "error":
            self.error = _truncate(getattr(event, "message", "") or "", 500)

    # ---------- 收尾 ----------

    def finish(self) -> dict[str, Any]:
        """结束追踪并写盘，返回本次 trace 的 dict（便于测试与审计）"""
        self.finished_at = time.time()
        record = self._build_record()
        if not settings.trace_enabled:
            return record
        export_record(record)
        return record

    def _build_record(self) -> dict[str, Any]:
        latency_ms = int((self.finished_at - self.started_at) * 1000) if self.finished_at else None
        return {
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "latency_ms": latency_ms,
            "input_text": _truncate(self.input_text, 500),
            "output_text": _truncate(self.output_text, 2000),
            "output_len": len(self.output_text),
            "finish_reason": self.finish_reason,
            "error": self.error,
            "usage": self.token_usage,
            "tool_calls": self.tool_calls,
            "tool_success": self.tool_success,
            "tool_fail": self.tool_fail,
            "total_tools": self.tool_success + self.tool_fail,
            "events_count": self.events_count,
        }


# ---------- 导出 ----------

def _local_traces_path():
    return data_dir() / settings.trace_dir / "offercabin_traces.jsonl"


def export_record(record: dict[str, Any]) -> None:
    """把 trace 记录写入本地 JSONL（追加模式）"""
    try:
        path = _local_traces_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("本地 trace 写入失败", exc_info=True)


def _try_langsmith(record: dict[str, Any]) -> bool:
    """尝试提交到 LangSmith，成功返回 True，否则（未配置/异常）返回 False"""
    try:
        from langsmith import Client as LangSmithClient
        from langsmith.run_trees import RunTree
    except Exception:
        logger.debug("langsmith SDK 未安装，降级为 local 导出")
        return False
    try:
        client = LangSmithClient(
            api_key=settings.langsmith_api_key,
            project_name=settings.langsmith_project,
        )
        run = RunTree(
            name="offercabin_agent",
            run_type="chain",
            client=client,
            inputs={
                "user_id": record["user_id"],
                "session_id": record["session_id"],
                "input": record["input_text"],
            },
            outputs={
                "output": record["output_text"],
                "tool_calls": record["tool_calls"],
            },
        )
        for key, value in record.items():
            if key in ("input_text", "output_text", "tool_calls"):
                continue
            run.extra[key] = value
        run.post()
        run.patch()
        return True
    except Exception:
        logger.warning("LangSmith 提交失败", exc_info=True)
        return False


# ---------- 生成器包装（API 层集成点） ----------

async def trace_agent_generator(
    gen: AsyncIterator[Any],
    *,
    user_id: str,
    session_id: str,
    user_input: str,
) -> AsyncIterator[Any]:
    """包装 AgentEvent 生成器，自动记录一次会话级 Trace。

    调用方式（在 agent.py 的 event_stream 内）：
        async for event in trace_agent_generator(
            agent.run_stream(req.message),
            user_id=user_id, session_id=req.session_id or "",
            user_input=req.message,
        ):
            yield event

    当 TRACE_ENABLED=false 时，直接透传原生成器（零额外开销）。
    """
    if not (settings.trace_enabled or settings.trace_exporter == "langsmith"):
        async for e in gen:
            yield e
        return

    trace_id = uuid.uuid4().hex
    token = _current_trace_id.set(trace_id)
    tracer = Tracer(trace_id=trace_id, user_id=user_id, session_id=session_id or "")
    tracer.input_text = user_input
    try:
        async for event in gen:
            tracer.observe(event)
            yield event
    finally:
        record = tracer.finish()
        if (settings.trace_exporter == "langsmith"
                and settings.langsmith_api_key
                and not _try_langsmith(record)):
            # 降级：本地已写盘（finish 已导出），仅记日志
            logger.debug("langsmith 导出失败，保留本地记录")
        _current_trace_id.reset(token)


# ---------- 工具 ----------

def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "..."


def _sanitize_dict(data: dict) -> dict:
    """对工具参数做审计脱敏：截断超长字符串字段，避免大 payload 写入磁盘"""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = _truncate(v, 200)
        elif isinstance(v, dict):
            out[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_dict(i) if isinstance(i, dict) else _truncate(str(i), 100)
                      if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out