"""
Agent API
- POST /api/v1/agent/chat: SSE 流式对话
- POST /api/v1/agent/confirm: 确认敏感操作
- GET  /api/v1/agent/sessions: 列出会话
- GET  /api/v1/agent/sessions/{id}: 获取会话详情
- DELETE /api/v1/agent/sessions/{id}: 删除会话
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db, SessionLocal
from app.core.llm import get_default_provider
from app.core.rate_limit import agent_rate_limit
from app.core.response import ok, BadRequestError, NotFoundError
from app.agent.apps import create_job_agent
from app.agent.runtime.events import (
    ContentDelta, ToolCallStart, ToolResultEvent,
    DoneEvent, ConfirmRequiredEvent, ErrorEvent,
)
from app.models.application import AgentSession
from app.core.log_utils import sanitize_for_log
from app.core.tracing import trace_agent_generator

logger = logging.getLogger("offercabin.api.agent")

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ============ Schemas ============

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    action_id: str
    approved: bool
    session_id: str


class RenameSessionRequest(BaseModel):
    title: str


# ============ SSE 辅助 ============

def _event_to_sse(event) -> str:
    """把 AgentEvent 序列化为 SSE 数据行"""
    data = event.model_dump(mode="json")
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _friendly_llm_error(e: Exception) -> str:
    """把异常转换为面向用户的友好提示。

    后台完整异常留在日志中，前端只展示分类化的可操作信息：
    - 鉴权失败 → 引导检查 API Key
    - 限流     → 引导稍后重试
    - 网络     → 引导检查网络与 Base URL
    - 未知     → 通用兜底
    """
    from app.core.llm import (
        LLMError, AuthenticationError, RateLimitError, NetworkError,
        InvalidRequestError, ContentFilterError,
    )
    if isinstance(e, AuthenticationError):
        return "LLM 鉴权失败：API Key 无效或已过期，请到「设置 → LLM 配置」检查。"
    if isinstance(e, RateLimitError):
        return "LLM 服务限流或繁忙，请稍后再试。"
    if isinstance(e, NetworkError):
        return "LLM 网络连接失败，请检查网络或 Base URL 是否正确。"
    if isinstance(e, ContentFilterError):
        return "本次内容的回复触发了内容审核，请换个说法重试。"
    if isinstance(e, InvalidRequestError):
        return f"LLM 请求不被接受（{getattr(e, 'message', '参数有误')}），请检查模型名称是否正确。"
    if isinstance(e, LLMError):
        return f"LLM 调用失败（{type(e).__name__}），可到「设置 → LLM 配置」测试连通性排查。"
    return "对话生成失败：请稍后重试，或检查 LLM 配置。"


async def _agent_stream(agent, user_id: str, session_id: str, user_input: str):
    """包装 Agent 流，挂载 Tracer"""
    async for event in trace_agent_generator(
        agent.run_stream(user_input),
        user_id=user_id,
        session_id=session_id,
        user_input=user_input,
    ):
        yield event


# ============ 路由 ============

@router.post("/chat", dependencies=[Depends(agent_rate_limit)])
async def agent_chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Agent 对话接口（SSE 流式响应）

    事件类型：
    - content_delta: 文本增量 {"type":"content_delta","delta":"..."}
    - tool_call_start: 工具调用开始
    - tool_result: 工具执行结果
    - confirm_required: 需要用户确认
    - done: 完成
    - error: 错误

    Session 生命周期策略：
    - 不使用 Depends(get_db)（会在 SSE 长连接期间独占 session）
    - 在流内部为每次 agent 运行创建独立短 session，结束后立即关闭
    - 工具调用内部按需另开 session，避免长连接独占
    """
    logger.info(f"用户 {user_id} 发起对话，消息长度={len(req.message)}，session_id={req.session_id or 'new'}")
    logger.debug(f"对话内容预览: {sanitize_for_log(req.message[:80])}")

    async def event_stream():
        # 为本次 agent 运行创建独立 session，流结束后立即关闭
        db = SessionLocal()
        try:
            llm = get_default_provider()
            agent = create_job_agent(
                llm=llm,
                db=db,
                user_id=user_id,
                session_id=req.session_id,
            )
            try:
                async for event in _agent_stream(agent, user_id, req.session_id or "", req.message):
                    yield _event_to_sse(event)
            except Exception as e:
                logger.exception(f"Agent 流式异常: {e}")
                # 向用户返回分类友好提示，避免暴露底层错误细节（含 base_url / key 片段）
                yield _event_to_sse(ErrorEvent(message=_friendly_llm_error(e)))
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 不缓冲
        },
    )


@router.post("/confirm")
async def confirm_action(
    req: ConfirmRequest,
    user_id: str = Depends(get_current_user),
):
    """
    确认敏感操作后恢复执行（SSE 流式）

    用户在前端点击"确认/取消"后调用此接口，agent 会恢复运行
    """
    logger.info(f"用户 {user_id} 确认操作 action_id={req.action_id} approved={req.approved}")

    async def event_stream():
        db = SessionLocal()
        try:
            llm = get_default_provider()
            agent = create_job_agent(
                llm=llm,
                db=db,
                user_id=user_id,
                session_id=req.session_id,
            )
            try:
                async for event in agent.resume_after_confirm(req.action_id, req.approved):
                    yield _event_to_sse(event)
            except Exception as e:
                logger.exception(f"Agent 恢复异常: {e}")
                yield _event_to_sse(ErrorEvent(message=_friendly_llm_error(e)))
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/sessions")
async def list_sessions(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    """列出用户的所有会话（含消息数与最后一条消息预览，便于区分会话）"""
    sessions = db.query(AgentSession).filter(
        AgentSession.user_id == user_id
    ).order_by(AgentSession.updated_at.desc().nullslast()).limit(limit).all()

    data = []
    for s in sessions:
        messages = []
        try:
            messages = json.loads(s.messages or "[]")
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"会话 {s.id} 消息解析失败: {e}")
            messages = []

        # 取最后一条用户/助手消息的文本作为预览
        preview = ""
        for msg in reversed(messages):
            content = msg.get("content") or msg.get("text") or ""
            if isinstance(content, list):
                # 兼容多段 content 结构
                content = "".join(
                    seg.get("text", "") for seg in content if isinstance(seg, dict)
                )
            if content:
                preview = content[:60]
                break

        data.append({
            "id": str(s.id),
            "title": s.title or "未命名会话",
            "message_count": len(messages),
            "preview": preview,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    return ok(data, message="获取会话列表成功")


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: RenameSessionRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重命名会话标题"""
    title = body.title.strip()
    if not title:
        raise BadRequestError("标题不能为空")
    if len(title) > 100:
        raise BadRequestError("标题过长（最多 100 字符）")

    sess = db.query(AgentSession).filter(
        AgentSession.id == session_id,
        AgentSession.user_id == user_id,
    ).first()
    if not sess:
        raise NotFoundError("会话不存在")

    sess.title = title
    db.commit()
    return ok({"id": str(sess.id), "title": sess.title}, message="重命名成功")

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取会话详情（含完整消息历史）"""
    sess = db.query(AgentSession).filter(
        AgentSession.id == session_id,
        AgentSession.user_id == user_id,
    ).first()
    if not sess:
        raise NotFoundError("会话不存在")

    try:
        messages = json.loads(sess.messages or "[]")
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"会话 {session_id} 消息解析失败: {e}")
        messages = []
    return ok({
        "id": str(sess.id),
        "title": sess.title,
        "messages": messages,
        "created_at": sess.created_at.isoformat() if sess.created_at else None,
        "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
    }, message="获取会话详情成功")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除会话"""
    sess = db.query(AgentSession).filter(
        AgentSession.id == session_id,
        AgentSession.user_id == user_id,
    ).first()
    if not sess:
        raise NotFoundError("会话不存在")

    db.delete(sess)
    db.commit()
    return ok(None, message="会话已删除")
