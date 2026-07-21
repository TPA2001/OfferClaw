"""
投递记录 REST API
提供看板所需的直接 CRUD 接口（区别于 Agent 工具调用）
针对校招/社招真实场景进行了细化：
- 拒绝环节追踪（简历挂/笔试挂/一面挂/...）
- 面试轮次与下一面试时间
- offer 接受状态
- 优先级标记
- 漏斗统计 + 跟进提醒
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.application import Application


router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


# ============ 常量 ============

# 合法状态枚举（与 agent tools 保持一致）
VALID_STATUSES = {
    "applied": "已投递",
    "assessment": "笔试中",
    "interview": "面试中",
    "offer": "已录用",
    "rejected": "已拒绝",
    "withdrawn": "已撤回",
}

# 拒绝环节枚举（校招/社招真实痛点）
REJECTION_STAGES = {
    "resume_rejected": "简历初筛挂",
    "assessment_failed": "笔试挂",
    "interview_1_failed": "一面挂",
    "interview_2_failed": "二面挂",
    "interview_3_failed": "三面挂",
    "hr_failed": "HR 面挂",
    "offer_collapsed": "offer 谈崩",
    "hc_empty": "HC 没有",
    "self_withdraw": "主动放弃",
    "other": "其他",
}

# 面试轮次标签
INTERVIEW_ROUND_LABELS = {
    1: "一面",
    2: "二面",
    3: "三面",
    4: "HR 面",
    5: "加面",
}

# offer 状态
OFFER_STATUSES = {
    "pending": "待回复",
    "accepted": "已接受",
    "declined": "已拒绝 offer",
}

# 优先级
PRIORITIES = {
    "high": "心仪",
    "medium": "普通",
    "low": "备选",
}

# 长时间未回复阈值（天）
STALE_THRESHOLD_DAYS = 7


# ============ Schemas ============

class ApplicationCreate(BaseModel):
    company: str
    position: str
    job_url: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    status: str = "applied"
    rejection_stage: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[str] = None  # ISO 字符串
    assessment_deadline: Optional[str] = None  # 笔试截止时间
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[str] = None  # 签约 deadline
    hr_contact: Optional[str] = None
    priority: str = "medium"


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    job_url: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None
    rejection_stage: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[str] = None
    assessment_deadline: Optional[str] = None
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[str] = None
    hr_contact: Optional[str] = None
    priority: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    company: str
    position: str
    job_url: Optional[str] = None
    source: Optional[str] = None
    status: str
    status_label: str
    rejection_stage: Optional[str] = None
    rejection_stage_label: Optional[str] = None
    interview_round: Optional[int] = None
    interview_round_label: Optional[str] = None
    next_interview_at: Optional[str] = None
    assessment_deadline: Optional[str] = None
    offer_status: Optional[str] = None
    offer_status_label: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[str] = None
    hr_contact: Optional[str] = None
    priority: Optional[str] = None
    priority_label: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    sort_order: int = 0


def _to_dict(a: Application) -> dict:
    """ORM 对象转字典，附带可读 label"""
    return {
        "id": str(a.id),
        "company": a.company,
        "position": a.position,
        "job_url": a.job_url,
        "source": a.source,
        "status": a.status,
        "status_label": VALID_STATUSES.get(a.status, a.status),
        "rejection_stage": a.rejection_stage,
        "rejection_stage_label": REJECTION_STAGES.get(a.rejection_stage, a.rejection_stage) if a.rejection_stage else None,
        "interview_round": a.interview_round,
        "interview_round_label": INTERVIEW_ROUND_LABELS.get(a.interview_round, str(a.interview_round)) if a.interview_round else None,
        "next_interview_at": a.next_interview_at.isoformat() if a.next_interview_at else None,
        "assessment_deadline": a.assessment_deadline.isoformat() if a.assessment_deadline else None,
        "offer_status": a.offer_status,
        "offer_status_label": OFFER_STATUSES.get(a.offer_status) if a.offer_status else None,
        "offer_salary": a.offer_salary,
        "offer_location": a.offer_location,
        "offer_deadline": a.offer_deadline.isoformat() if a.offer_deadline else None,
        "hr_contact": a.hr_contact,
        "priority": a.priority or "medium",
        "priority_label": PRIORITIES.get(a.priority or "medium", a.priority),
        "notes": a.notes,
        "tags": a.tags,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "sort_order": a.sort_order or 0,
    }


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    """从 ISO 字符串解析为 datetime，容错"""
    if not val:
        return None
    try:
        # 处理 'Z' 后缀
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _validate_sub_fields(status: str, body_dict: dict, is_create: bool = False):
    """校验细化字段与 status 的对应关系（软校验，不抛异常只清理）"""
    # 非 rejected 状态清空 rejection_stage（除非用户显式传了，那也接受）
    # 这里采用宽松策略：只在创建时清理，更新时尊重用户输入
    pass


# ============ 路由 ============

@router.get("/")
async def list_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    company: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出投递记录，可按状态/公司/优先级过滤"""
    q = db.query(Application).filter(Application.user_id == user_id)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"非法状态: {status_filter}")
        q = q.filter(Application.status == status_filter)
    if company:
        q = q.filter(Application.company.like(f"%{company}%"))
    if priority:
        if priority not in PRIORITIES:
            raise HTTPException(status_code=400, detail=f"非法优先级: {priority}")
        q = q.filter(Application.priority == priority)

    total = q.count()
    apps = q.order_by(
        # 心仪公司优先
        Application.priority.asc(),  # high < medium < low 字母序恰好对应
        Application.sort_order.asc(),
        Application.updated_at.desc().nullslast(),
    ).offset(offset).limit(limit).all()

    return {
        "code": 0,
        "data": [_to_dict(a) for a in apps],
        "total": total,
    }


@router.post("/")
async def create_application(
    body: ApplicationCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建投递记录"""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态: {body.status}")
    if body.priority and body.priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail=f"非法优先级: {body.priority}")
    if body.rejection_stage and body.rejection_stage not in REJECTION_STAGES:
        raise HTTPException(status_code=400, detail=f"非法拒绝环节: {body.rejection_stage}")
    if body.offer_status and body.offer_status not in OFFER_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法 offer 状态: {body.offer_status}")

    app = Application(
        id=str(uuid.uuid4()),
        user_id=user_id,
        company=body.company,
        position=body.position,
        job_url=body.job_url,
        source=body.source,
        notes=body.notes,
        tags=body.tags,
        status=body.status,
        rejection_stage=body.rejection_stage,
        interview_round=body.interview_round,
        next_interview_at=_parse_dt(body.next_interview_at),
        assessment_deadline=_parse_dt(body.assessment_deadline),
        offer_status=body.offer_status,
        offer_salary=body.offer_salary,
        offer_location=body.offer_location,
        offer_deadline=_parse_dt(body.offer_deadline),
        hr_contact=body.hr_contact,
        priority=body.priority or "medium",
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"code": 0, "data": _to_dict(app)}


@router.get("/{application_id}")
async def get_application(
    application_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单条投递记录"""
    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"code": 0, "data": _to_dict(app)}


@router.put("/{application_id}")
async def update_application(
    application_id: str,
    body: ApplicationUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新投递记录（支持部分更新）"""
    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="记录不存在")

    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"非法状态: {body.status}")
        app.status = body.status
        # 状态切换时自动清理不相关字段
        if body.status != "rejected":
            app.rejection_stage = None
        if body.status != "interview":
            app.interview_round = None
            app.next_interview_at = None
        if body.status != "assessment":
            app.assessment_deadline = None
        if body.status != "offer":
            app.offer_status = None
            app.offer_salary = None
            app.offer_location = None
            app.offer_deadline = None

    if body.rejection_stage is not None:
        if body.rejection_stage not in REJECTION_STAGES:
            raise HTTPException(status_code=400, detail=f"非法拒绝环节: {body.rejection_stage}")
        app.rejection_stage = body.rejection_stage
    if body.interview_round is not None:
        if body.interview_round < 1 or body.interview_round > 5:
            raise HTTPException(status_code=400, detail="面试轮次必须在 1-5 之间")
        app.interview_round = body.interview_round
    if body.next_interview_at is not None:
        app.next_interview_at = _parse_dt(body.next_interview_at)
    if body.assessment_deadline is not None:
        app.assessment_deadline = _parse_dt(body.assessment_deadline)
    if body.offer_status is not None:
        if body.offer_status not in OFFER_STATUSES:
            raise HTTPException(status_code=400, detail=f"非法 offer 状态: {body.offer_status}")
        app.offer_status = body.offer_status
    if body.offer_salary is not None:
        app.offer_salary = body.offer_salary
    if body.offer_location is not None:
        app.offer_location = body.offer_location
    if body.offer_deadline is not None:
        app.offer_deadline = _parse_dt(body.offer_deadline)
    if body.hr_contact is not None:
        app.hr_contact = body.hr_contact
    if body.priority is not None:
        if body.priority not in PRIORITIES:
            raise HTTPException(status_code=400, detail=f"非法优先级: {body.priority}")
        app.priority = body.priority

    if body.company is not None:
        app.company = body.company
    if body.position is not None:
        app.position = body.position
    if body.job_url is not None:
        app.job_url = body.job_url
    if body.source is not None:
        app.source = body.source
    if body.notes is not None:
        app.notes = body.notes
    if body.tags is not None:
        app.tags = body.tags

    db.commit()
    db.refresh(app)
    return {"code": 0, "data": _to_dict(app)}


@router.patch("/{application_id}/status")
async def update_status(
    application_id: str,
    new_status: str = Query(..., description="新状态"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """快速更新状态（看板拖拽用，允许任意状态切换）"""
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法状态: {new_status}")

    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="记录不存在")

    old_status = app.status
    app.status = new_status
    # 切换状态时清理不相关字段
    if new_status != "rejected":
        app.rejection_stage = None
    if new_status != "interview":
        app.interview_round = None
        app.next_interview_at = None
    if new_status != "assessment":
        app.assessment_deadline = None
    if new_status != "offer":
        app.offer_status = None
        app.offer_salary = None
        app.offer_location = None
        app.offer_deadline = None

    db.commit()
    db.refresh(app)
    return {
        "code": 0,
        "data": _to_dict(app),
        "old_status": old_status,
    }


@router.delete("/{application_id}")
async def delete_application(
    application_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除投递记录"""
    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="记录不存在")

    db.delete(app)
    db.commit()
    return {"code": 0, "message": "已删除"}


@router.post("/batch")
async def batch_import(
    items: List[ApplicationCreate],
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量导入投递记录"""
    created = []
    for item in items:
        if item.status not in VALID_STATUSES:
            continue
        app = Application(
            id=str(uuid.uuid4()),
            user_id=user_id,
            company=item.company,
            position=item.position,
            job_url=item.job_url,
            source=item.source,
            notes=item.notes,
            tags=item.tags,
            status=item.status,
            rejection_stage=item.rejection_stage,
            interview_round=item.interview_round,
            next_interview_at=_parse_dt(item.next_interview_at),
            assessment_deadline=_parse_dt(item.assessment_deadline),
            offer_status=item.offer_status,
            offer_salary=item.offer_salary,
            offer_location=item.offer_location,
            offer_deadline=_parse_dt(item.offer_deadline),
            hr_contact=item.hr_contact,
            priority=item.priority or "medium",
        )
        db.add(app)
        created.append(app)
    db.commit()
    return {"code": 0, "data": {"imported": len(created)}}


@router.get("/stats/overview")
async def get_stats(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """看板统计概览"""
    from collections import Counter

    apps = db.query(Application).filter(
        Application.user_id == user_id
    ).all()

    total = len(apps)
    if total == 0:
        return {
            "code": 0,
            "data": {
                "total": 0,
                "by_status": {},
                "by_status_raw": {},
                "by_rejection_stage": {},
                "by_source": {},
                "funnel": {},
                "reply_rate": "0%",
                "offer_rate": "0%",
                "avg_wait_days": 0,
                "waiting_count": 0,
                "stale_count": 0,
                "upcoming_interviews": 0,
                "pending_assessments": 0,
                "priority_breakdown": {"high": 0, "medium": 0, "low": 0},
            },
        }

    status_counter = Counter(a.status for a in apps)
    offer_count = status_counter.get("offer", 0)
    replied = sum(status_counter.get(s, 0) for s in ["assessment", "interview", "offer", "rejected"])
    reply_rate = replied / total
    offer_rate = offer_count / total

    now = datetime.now(timezone.utc)

    # 漏斗统计：投递 → 简历通过 → 笔试通过 → 面试 → offer
    # 简历通过 = 进入过笔试/面试/offer 的（不算纯简历挂）
    resume_passed = sum(1 for a in apps if a.status in ("assessment", "interview", "offer") or
                       (a.status == "rejected" and a.rejection_stage and a.rejection_stage not in ("resume_rejected",)))
    assessment_passed = sum(1 for a in apps if a.status in ("interview", "offer") or
                           (a.status == "rejected" and a.rejection_stage and
                            a.rejection_stage not in ("resume_rejected", "assessment_failed")))
    interview_passed = sum(1 for a in apps if a.status == "offer" or
                          (a.status == "rejected" and a.rejection_stage and
                           a.rejection_stage not in ("resume_rejected", "assessment_failed",
                                                     "interview_1_failed", "interview_2_failed",
                                                     "interview_3_failed", "hr_failed")))

    funnel = {
        "applied": total,
        "resume_passed": resume_passed,
        "assessment_passed": assessment_passed,
        "interview_passed": interview_passed,
        "offer": offer_count,
    }

    # 拒绝环节统计
    rejection_counter = Counter(
        a.rejection_stage or "other" for a in apps if a.status == "rejected"
    )

    # 等待时间
    waiting_days = []
    stale_count = 0
    upcoming_interviews = 0
    pending_assessments = 0
    for a in apps:
        if a.applied_at and a.status in ("applied", "assessment"):
            applied = a.applied_at
            if applied.tzinfo is None:
                applied = applied.replace(tzinfo=timezone.utc)
            days = (now - applied).days
            if days >= 0:
                waiting_days.append(days)
                if days >= STALE_THRESHOLD_DAYS and a.status == "applied":
                    stale_count += 1
        # 即将到来的面试（未来 7 天内）
        if a.next_interview_at and a.status == "interview":
            interview_dt = a.next_interview_at
            if interview_dt.tzinfo is None:
                interview_dt = interview_dt.replace(tzinfo=timezone.utc)
            delta_hours = (interview_dt - now).total_seconds() / 3600
            if -24 <= delta_hours <= 7 * 24:  # 1天内已开始到未来7天
                upcoming_interviews += 1
        # 笔试 deadline（未来 7 天内未完成）
        if a.assessment_deadline and a.status == "assessment":
            deadline_dt = a.assessment_deadline
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            delta_hours = (deadline_dt - now).total_seconds() / 3600
            if -24 <= delta_hours <= 7 * 24:
                pending_assessments += 1

    # 渠道效果统计：各来源的投递数 / 回复数 / 回复率
    source_stats = {}
    replied_statuses = {"assessment", "interview", "offer", "rejected"}
    for a in apps:
        src = a.source or "未指定"
        if src not in source_stats:
            source_stats[src] = {"total": 0, "replied": 0, "offer": 0}
        source_stats[src]["total"] += 1
        if a.status in replied_statuses:
            source_stats[src]["replied"] += 1
        if a.status == "offer":
            source_stats[src]["offer"] += 1
    # 计算回复率
    by_source = {}
    for src, vals in source_stats.items():
        rate = (vals["replied"] / vals["total"]) if vals["total"] else 0
        by_source[src] = {
            "total": vals["total"],
            "replied": vals["replied"],
            "offer": vals["offer"],
            "reply_rate": f"{rate * 100:.0f}%",
        }

    avg_wait = sum(waiting_days) / len(waiting_days) if waiting_days else 0

    # 优先级分布
    priority_counter = Counter(a.priority or "medium" for a in apps)

    return {
        "code": 0,
        "data": {
            "total": total,
            "by_status": {VALID_STATUSES.get(k, k): v for k, v in status_counter.items()},
            "by_status_raw": dict(status_counter),
            "by_rejection_stage": {
                REJECTION_STAGES.get(k, k): v for k, v in rejection_counter.items()
            },
            "by_rejection_stage_raw": dict(rejection_counter),
            "by_source": by_source,
            "funnel": funnel,
            "offer_count": offer_count,
            "rejected_count": status_counter.get("rejected", 0),
            "reply_rate": f"{reply_rate * 100:.1f}%",
            "offer_rate": f"{offer_rate * 100:.1f}%",
            "avg_wait_days": round(avg_wait, 1),
            "waiting_count": len(waiting_days),
            "stale_count": stale_count,
            "upcoming_interviews": upcoming_interviews,
            "pending_assessments": pending_assessments,
            "priority_breakdown": {
                "high": priority_counter.get("high", 0),
                "medium": priority_counter.get("medium", 0),
                "low": priority_counter.get("low", 0),
            },
        },
    }


@router.get("/stats/followups")
async def get_followups(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跟进提醒：列出需要关注的项目
    - 长时间未回复的投递（>= 7 天）
    - 即将到来的笔试 deadline（未来 7 天）
    - 即将到来的面试（未来 7 天）
    - 待回复的 offer
    """
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=STALE_THRESHOLD_DAYS)
    upcoming_end = now + timedelta(days=7)
    past_24h = now - timedelta(days=1)

    apps = db.query(Application).filter(
        Application.user_id == user_id
    ).all()

    stale_apps = []
    upcoming = []
    pending_offers = []
    pending_assessments = []

    for a in apps:
        # 长时间未回复
        if a.status == "applied" and a.applied_at:
            applied = a.applied_at
            if applied.tzinfo is None:
                applied = applied.replace(tzinfo=timezone.utc)
            if applied < stale_threshold:
                days = (now - applied).days
                stale_apps.append({**_to_dict(a), "stale_days": days})
        # 即将笔试
        if a.status == "assessment" and a.assessment_deadline:
            deadline_dt = a.assessment_deadline
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            if past_24h <= deadline_dt <= upcoming_end:
                delta = deadline_dt - now
                hours = delta.total_seconds() / 3600
                pending_assessments.append({
                    **_to_dict(a),
                    "hours_until": round(hours, 1),
                    "when": deadline_dt.isoformat(),
                })
        # 即将面试
        if a.status == "interview" and a.next_interview_at:
            interview_dt = a.next_interview_at
            if interview_dt.tzinfo is None:
                interview_dt = interview_dt.replace(tzinfo=timezone.utc)
            if past_24h <= interview_dt <= upcoming_end:
                delta = interview_dt - now
                hours = delta.total_seconds() / 3600
                upcoming.append({
                    **_to_dict(a),
                    "hours_until": round(hours, 1),
                    "when": interview_dt.isoformat(),
                })
        # 待回复 offer
        if a.status == "offer" and a.offer_status == "pending":
            pending_offers.append(_to_dict(a))

    # 排序
    stale_apps.sort(key=lambda x: -x["stale_days"])
    pending_assessments.sort(key=lambda x: x["hours_until"])
    upcoming.sort(key=lambda x: x["hours_until"])

    return {
        "code": 0,
        "data": {
            "stale": stale_apps,
            "pending_assessments": pending_assessments,
            "upcoming_interviews": upcoming,
            "pending_offers": pending_offers,
            "total_alerts": len(stale_apps) + len(pending_assessments) + len(upcoming) + len(pending_offers),
        },
    }
