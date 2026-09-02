"""
求职日志 API
提供面试复盘、求职笔记、周报的 CRUD 与 LLM 分析接口
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.response import ok, NotFoundError, BadRequestError, InternalServerError
from app.core.llm import get_gen_provider
from app.features.journal import JournalEntry, JournalService

logger = logging.getLogger("offercabin.api.journal")

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class JournalEntryCreate(BaseModel):
    """创建日志条目"""
    entry_type: str  # note / interview_review / mood_check / weekly_summary
    title: Optional[str] = None
    content: str
    application_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    mood_score: Optional[str] = None


class JournalEntryUpdate(BaseModel):
    """更新日志条目"""
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    mood_score: Optional[str] = None


class InterviewReviewRequest(BaseModel):
    """面试复盘请求"""
    interview_notes: str
    position: Optional[str] = None
    company: Optional[str] = None


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------

def serialize_entry(e: JournalEntry) -> dict:
    return {
        "id": e.id,
        "entry_type": e.entry_type,
        "title": e.title,
        "content": e.content,
        "application_id": e.application_id,
        "metadata": e.meta or {},
        "mood_score": e.mood_score,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/entries")
async def list_entries(
    entry_type: Optional[str] = Query(None, description="按类型筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询日志条目列表"""
    q = db.query(JournalEntry).filter(JournalEntry.user_id == user_id)
    if entry_type:
        q = q.filter(JournalEntry.entry_type == entry_type)
    total = q.count()
    items = q.order_by(JournalEntry.created_at.desc()).offset(offset).limit(limit).all()
    return ok({
        "items": [serialize_entry(e) for e in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.get("/entries/{entry_id}")
async def get_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询单条日志"""
    e = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.user_id == user_id,
    ).first()
    if not e:
        raise NotFoundError("日志不存在")
    return ok(serialize_entry(e))


@router.post("/entries")
async def create_entry(
    body: JournalEntryCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建日志条目"""
    if body.entry_type not in ("note", "interview_review", "mood_check", "weekly_summary"):
        raise BadRequestError(f"无效的日志类型: {body.entry_type}")
    if not body.content or not body.content.strip():
        raise BadRequestError("日志内容不能为空")

    e = JournalEntry(
        user_id=user_id,
        entry_type=body.entry_type,
        title=body.title,
        content=body.content.strip(),
        application_id=body.application_id,
        meta=body.metadata or {},
        mood_score=body.mood_score if body.entry_type == "mood_check" else None,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return ok(serialize_entry(e))


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    body: JournalEntryUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新日志条目"""
    e = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.user_id == user_id,
    ).first()
    if not e:
        raise NotFoundError("日志不存在")

    if body.title is not None:
        e.title = body.title
    if body.content is not None:
        e.content = body.content
    if body.metadata is not None:
        e.meta = body.metadata
    if body.mood_score is not None:
        e.mood_score = body.mood_score

    db.commit()
    db.refresh(e)
    return ok(serialize_entry(e))


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除日志条目"""
    e = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.user_id == user_id,
    ).first()
    if not e:
        raise NotFoundError("日志不存在")
    db.delete(e)
    db.commit()
    return ok({"message": "已删除", "id": entry_id})


# ---------------------------------------------------------------------------
# LLM 面试复盘
# ---------------------------------------------------------------------------

@router.post("/review-interview")
async def review_interview(
    body: InterviewReviewRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    LLM 辅助面试复盘

    输入面试笔记，返回结构化分析：
    summary / strengths / weaknesses / suggestions / score / questions
    """
    if not body.interview_notes or not body.interview_notes.strip():
        raise BadRequestError("面试笔记不能为空")

    try:
        llm = get_gen_provider()
        service = JournalService(llm)
        result = await service.review_interview(
            interview_notes=body.interview_notes,
            position=body.position,
            company=body.company,
        )
        return ok(result)
    except Exception as e:
        logger.exception("面试复盘失败: %s", e)
        raise InternalServerError(f"面试复盘失败: {e}")


# ---------------------------------------------------------------------------
# 周报生成
# ---------------------------------------------------------------------------

@router.get("/weekly-summary")
async def weekly_summary(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    生成本周求职周报

    汇总过去 7 天的投递/面试/日志数据，LLM 生成结构化周报
    """
    try:
        llm = get_gen_provider()
        service = JournalService(llm)
        result = await service.generate_weekly_summary(
            user_id=user_id,
            db=db,
        )
        return ok(result)
    except Exception as e:
        logger.exception("周报生成失败: %s", e)
        raise InternalServerError(f"周报生成失败: {e}")
