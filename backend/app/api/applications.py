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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.response import ok, BadRequestError, NotFoundError
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
    rejection_reason: Optional[str] = None  # 拒绝补充说明（自由文本）
    assessment_type: Optional[str] = None   # 笔试类型（在线编程/行测/性格测试）
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
    rejection_reason: Optional[str] = None
    assessment_type: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[str] = None
    assessment_deadline: Optional[str] = None
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[str] = None
    hr_contact: Optional[str] = None
    priority: Optional[str] = None
    sort_order: Optional[int] = None


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
        "rejection_reason": a.rejection_reason,
        "assessment_type": a.assessment_type,
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
        "status_history": a.status_history or [],
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


def _cleanup_status_fields(app: Application, status: str) -> None:
    """根据状态清理不相关的子字段（用于状态切换时保持数据一致性）"""
    if status != "rejected":
        app.rejection_stage = None
        app.rejection_reason = None
    if status != "interview":
        app.interview_round = None
        app.next_interview_at = None
    if status != "assessment":
        app.assessment_deadline = None
        app.assessment_type = None
    if status != "offer":
        app.offer_status = None
        app.offer_salary = None
        app.offer_location = None
        app.offer_deadline = None


def _append_status_history(app: Application, old_status: Optional[str], new_status: str, note: Optional[str] = None) -> None:
    """追加一条状态变更记录到 status_history"""
    history = list(app.status_history or [])
    history.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "from": old_status,
        "to": new_status,
        "note": note,
    })
    app.status_history = history


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
            raise BadRequestError(f"非法状态: {status_filter}")
        q = q.filter(Application.status == status_filter)
    if company:
        q = q.filter(Application.company.like(f"%{company}%"))
    if priority:
        if priority not in PRIORITIES:
            raise BadRequestError(f"非法优先级: {priority}")
        q = q.filter(Application.priority == priority)

    total = q.count()
    apps = q.order_by(
        # 心仪公司优先
        Application.priority.asc(),  # high < medium < low 字母序恰好对应
        Application.sort_order.asc(),
        Application.updated_at.desc().nullslast(),
    ).offset(offset).limit(limit).all()

    return ok(
        [_to_dict(a) for a in apps],
        message="获取投递列表成功",
        extra={"total": total},
    )


@router.get("/search")
async def search_applications(
    q: str = Query(..., min_length=1, description="搜索关键字（公司/职位/备注/标签）"),
    limit: int = Query(50, le=200),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全文搜索投递记录（公司/职位/备注/标签）

    投递记录变多后必备能力：快速定位某公司/某岗位/某标签的历史投递。
    """
    kw = f"%{q.strip()}%"
    query = db.query(Application).filter(
        Application.user_id == user_id,
        or_(
            Application.company.like(kw),
            Application.position.like(kw),
            Application.notes.like(kw),
            Application.tags.like(kw),
        ),
    ).order_by(Application.updated_at.desc().nullslast()).limit(limit)

    apps = query.all()
    return ok(
        [_to_dict(a) for a in apps],
        message="搜索成功",
        extra={"total": len(apps), "query": q},
    )


@router.get("/export/csv")
async def export_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出投递记录为 CSV（UTF-8 BOM，Excel 友好）

    数据可移植刚需：用户可能要在 Excel 里二次分析，或迁移到其他工具。
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    query = db.query(Application).filter(Application.user_id == user_id)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise BadRequestError(f"非法状态: {status_filter}")
        query = query.filter(Application.status == status_filter)
    apps = query.order_by(Application.applied_at.desc().nullslast()).all()

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM，确保 Excel 正确识别中文
    writer = csv.writer(output)
    writer.writerow([
        "公司", "职位", "状态", "拒绝环节", "面试轮次", "下一面试时间",
        "笔试截止", "Offer状态", "薪资", "地点", "Offer截止", "HR联系方式",
        "优先级", "来源", "标签", "投递时间", "更新时间", "备注", "链接",
    ])
    for a in apps:
        writer.writerow([
            a.company, a.position,
            VALID_STATUSES.get(a.status, a.status),
            REJECTION_STAGES.get(a.rejection_stage, a.rejection_stage or "") if a.rejection_stage else "",
            INTERVIEW_ROUND_LABELS.get(a.interview_round, str(a.interview_round)) if a.interview_round else "",
            a.next_interview_at.isoformat() if a.next_interview_at else "",
            a.assessment_deadline.isoformat() if a.assessment_deadline else "",
            OFFER_STATUSES.get(a.offer_status, a.offer_status or "") if a.offer_status else "",
            a.offer_salary or "", a.offer_location or "",
            a.offer_deadline.isoformat() if a.offer_deadline else "",
            a.hr_contact or "",
            PRIORITIES.get(a.priority or "medium", a.priority or ""),
            a.source or "", a.tags or "",
            a.applied_at.isoformat() if a.applied_at else "",
            a.updated_at.isoformat() if a.updated_at else "",
            a.notes or "", a.job_url or "",
        ])

    content = output.getvalue().encode("utf-8")
    filename = f"offerclaw_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats/timeline")
async def get_timeline(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """投递时间趋势（按日聚合，近 N 天）

    用于复盘求职节奏：是否持续投递、周末是否懈怠、哪天集中投递。
    """
    start = datetime.now(timezone.utc) - timedelta(days=days)
    apps = db.query(Application).filter(
        Application.user_id == user_id,
        Application.applied_at >= start,
    ).all()

    # 按日期聚合（用 applied_at 的日期部分）
    daily: Dict[str, Dict[str, int]] = {}
    replied_statuses = {"assessment", "interview", "offer", "rejected"}
    for a in apps:
        if not a.applied_at:
            continue
        dt = a.applied_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily:
            daily[day_key] = {"applied": 0, "replied": 0, "offer": 0}
        daily[day_key]["applied"] += 1
        if a.status in replied_statuses:
            daily[day_key]["replied"] += 1
        if a.status == "offer":
            daily[day_key]["offer"] += 1

    # 补全空日期（连续序列，便于前端画图）
    timeline = []
    cursor = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    end_date = datetime.now(timezone.utc).date()
    while cursor <= end_date:
        key = cursor.strftime("%Y-%m-%d")
        info = daily.get(key, {"applied": 0, "replied": 0, "offer": 0})
        timeline.append({"date": key, **info})
        cursor = cursor + timedelta(days=1)

    total_applied = sum(d["applied"] for d in daily.values())
    return ok({
        "days": days,
        "timeline": timeline,
        "total_applied": total_applied,
        "total_replied": sum(d["replied"] for d in daily.values()),
        "total_offer": sum(d["offer"] for d in daily.values()),
        "avg_per_day": round(total_applied / days, 1) if days else 0,
    }, message="获取时间趋势成功")


@router.get("/stats/by-company")
async def get_by_company(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """公司维度统计（按公司聚合投递数/回复数/Offer数）

    用于复盘：哪些公司回复积极、哪些公司石沉大海、哪些公司给了 offer。
    """
    apps = db.query(Application).filter(Application.user_id == user_id).all()

    replied_statuses = {"assessment", "interview", "offer", "rejected"}
    companies: Dict[str, Dict[str, Any]] = {}
    for a in apps:
        key = a.company or "未知公司"
        if key not in companies:
            companies[key] = {
                "company": key,
                "total": 0, "replied": 0, "offer": 0, "rejected": 0,
                "positions": set(),
                "latest_status": None,
                "latest_at": None,
            }
        c = companies[key]
        c["total"] += 1
        c["positions"].add(a.position)
        if a.status in replied_statuses:
            c["replied"] += 1
        if a.status == "offer":
            c["offer"] += 1
        if a.status == "rejected":
            c["rejected"] += 1
        # 更新最新状态
        ap_dt = a.applied_at
        if ap_dt and (c["latest_at"] is None or ap_dt > c["latest_at"]):
            c["latest_at"] = ap_dt
            c["latest_status"] = a.status

    result = []
    for c in companies.values():
        # 历史脏数据 position 可能为 None，排序前过滤，避免 TypeError
        positions = sorted(p for p in c.pop("positions") if p is not None)
        latest_at = c.pop("latest_at")
        result.append({
            **c,
            "positions": positions,
            "position_count": len(positions),
            "reply_rate": f"{(c['replied'] / c['total'] * 100):.0f}%" if c["total"] else "0%",
            "offer_rate": f"{(c['offer'] / c['total'] * 100):.0f}%" if c["total"] else "0%",
            "latest_status_label": VALID_STATUSES.get(c["latest_status"], c["latest_status"]) if c["latest_status"] else None,
            "latest_at": latest_at.isoformat() if latest_at else None,
        })
    # 按投递数降序
    result.sort(key=lambda x: -x["total"])

    return ok({
        "companies": result,
        "total_companies": len(result),
    }, message="获取公司统计成功")


@router.post("/")
async def create_application(
    body: ApplicationCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建投递记录

    重复投递检测：同公司同岗位 30 天内已有记录时返回 warning（仍创建），
    避免求职大忌——同一岗位重复投递。前端可据此提示用户确认。
    """
    if body.status not in VALID_STATUSES:
        raise BadRequestError(f"非法状态: {body.status}")
    if body.priority and body.priority not in PRIORITIES:
        raise BadRequestError(f"非法优先级: {body.priority}")
    if body.rejection_stage and body.rejection_stage not in REJECTION_STAGES:
        raise BadRequestError(f"非法拒绝环节: {body.rejection_stage}")
    if body.offer_status and body.offer_status not in OFFER_STATUSES:
        raise BadRequestError(f"非法 offer 状态: {body.offer_status}")

    # 重复投递检测（同公司同岗位，30 天内，排除已撤回/已拒绝的）
    dup_warning = None
    dup_threshold = datetime.now(timezone.utc) - timedelta(days=30)
    existing = db.query(Application).filter(
        Application.user_id == user_id,
        Application.company == body.company,
        Application.position == body.position,
        Application.status.notin_(["withdrawn"]),
        or_(Application.applied_at >= dup_threshold, Application.applied_at.is_(None)),
    ).first()
    if existing:
        dup_warning = {
            "duplicate": True,
            "existing_id": str(existing.id),
            "existing_status": existing.status,
            "existing_status_label": VALID_STATUSES.get(existing.status, existing.status),
            "applied_at": existing.applied_at.isoformat() if existing.applied_at else None,
            "message": f"30 天内已投递过 {body.company} - {body.position}（当前状态：{VALID_STATUSES.get(existing.status, existing.status)}），请确认是否重复",
        }

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
        rejection_reason=body.rejection_reason,
        assessment_type=body.assessment_type,
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
    return ok(
        _to_dict(app),
        message="创建成功",
        extra={"warning": dup_warning},
    )


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
        raise NotFoundError("记录不存在")
    return ok(_to_dict(app))


@router.put("/{application_id}")
async def update_application(
    application_id: str,
    body: ApplicationUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新投递记录（支持部分更新；显式传 null 可清空对应字段）"""
    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise NotFoundError("记录不存在")

    # Pydantic v2：通过 model_fields_set 判断字段是否被显式传入（含 None）
    # 这样能区分「未提供」与「显式清空」
    provided = body.model_fields_set

    if "status" in provided:
        if body.status not in VALID_STATUSES:
            raise BadRequestError(f"非法状态: {body.status}")
        old_status = app.status
        app.status = body.status
        # 状态切换时自动清理不相关字段
        _cleanup_status_fields(app, body.status)
        # 追加状态变更历史
        _append_status_history(app, old_status, body.status)

    # 拒绝环节（显式传 null 可清空）
    if "rejection_stage" in provided:
        if body.rejection_stage is not None and body.rejection_stage not in REJECTION_STAGES:
            raise BadRequestError(f"非法拒绝环节: {body.rejection_stage}")
        app.rejection_stage = body.rejection_stage
    if "rejection_reason" in provided:
        app.rejection_reason = body.rejection_reason
    if "assessment_type" in provided:
        app.assessment_type = body.assessment_type
    if "interview_round" in provided:
        if body.interview_round is not None and (body.interview_round < 1 or body.interview_round > 5):
            raise BadRequestError("面试轮次必须在 1-5 之间")
        app.interview_round = body.interview_round
    if "next_interview_at" in provided:
        app.next_interview_at = _parse_dt(body.next_interview_at)
    if "assessment_deadline" in provided:
        app.assessment_deadline = _parse_dt(body.assessment_deadline)
    if "offer_status" in provided:
        if body.offer_status is not None and body.offer_status not in OFFER_STATUSES:
            raise BadRequestError(f"非法 offer 状态: {body.offer_status}")
        app.offer_status = body.offer_status
    if "offer_salary" in provided:
        app.offer_salary = body.offer_salary
    if "offer_location" in provided:
        app.offer_location = body.offer_location
    if "offer_deadline" in provided:
        app.offer_deadline = _parse_dt(body.offer_deadline)
    if "hr_contact" in provided:
        app.hr_contact = body.hr_contact
    if "priority" in provided:
        if body.priority is not None and body.priority not in PRIORITIES:
            raise BadRequestError(f"非法优先级: {body.priority}")
        app.priority = body.priority
    if "sort_order" in provided:
        app.sort_order = body.sort_order or 0

    # 基本字段（None 清空）
    for field in ("company", "position", "job_url", "source", "notes", "tags"):
        if field in provided:
            setattr(app, field, getattr(body, field))

    db.commit()
    db.refresh(app)
    return ok(_to_dict(app), message="更新成功")


@router.patch("/{application_id}/status")
async def update_status(
    application_id: str,
    new_status: str = Query(..., description="新状态"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """快速更新状态（看板拖拽用，允许任意状态切换）"""
    if new_status not in VALID_STATUSES:
        raise BadRequestError(f"非法状态: {new_status}")

    app = db.query(Application).filter(
        Application.id == application_id,
        Application.user_id == user_id,
    ).first()
    if not app:
        raise NotFoundError("记录不存在")

    old_status = app.status
    app.status = new_status
    # 切换状态时清理不相关字段
    _cleanup_status_fields(app, new_status)
    # 追加状态变更历史
    _append_status_history(app, old_status, new_status)

    db.commit()
    db.refresh(app)
    return ok(
        _to_dict(app),
        message="状态已更新",
        extra={"old_status": old_status},
    )


@router.patch("/reorder")
async def reorder_applications(
    orders: List[Dict[str, Any]],
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量更新排序（看板拖拽排序用）

    接收 [{"id": "...", "sort_order": 0}, ...]，按 sort_order 升序排列。
    """
    updated = 0
    for item in orders:
        app_id = item.get("id")
        so = item.get("sort_order", 0)
        if not app_id:
            continue
        app = db.query(Application).filter(
            Application.id == app_id,
            Application.user_id == user_id,
        ).first()
        if app:
            app.sort_order = so
            updated += 1
    db.commit()
    return ok({"updated": updated}, message="排序已更新")


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
        raise NotFoundError("记录不存在")

    db.delete(app)
    db.commit()
    return ok(None, message="已删除")


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
    return ok({"imported": len(created)}, message="批量导入完成")


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
        return ok({
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
        }, message="暂无投递记录")

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
        # 即将到来的面试：面试中的全部项目（与看板列/跟进提醒口径一致）
        if a.status == "interview":
            upcoming_interviews += 1
        # 待完成笔试：笔试中的全部项目（与看板列/跟进提醒口径一致）
        if a.status == "assessment":
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

    return ok({
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
    }, message="获取看板统计成功")


@router.get("/stats/followups")
async def get_followups(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跟进提醒：列出需要关注的项目

    与看板列状态保持一致（提醒数 = 对应列的卡片数）：
    - 长时间未回复的投递（>= 7 天，仅已投递状态）
    - 笔试中的所有项目（有截止时间的显示倒计时，无则提示未设置）
    - 面试中的所有项目（有面试时间的显示倒计时，无则提示未安排）
    - 待回复的 offer（offer_status 非 accepted/declined，含未填写）
    """
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=STALE_THRESHOLD_DAYS)

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
        # 笔试中：全部列出，与看板「笔试中」列一致
        if a.status == "assessment":
            item = _to_dict(a)
            if a.assessment_deadline:
                deadline_dt = a.assessment_deadline
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
                delta = deadline_dt - now
                hours = delta.total_seconds() / 3600
                item.update({
                    "hours_until": round(hours, 1),
                    "when": deadline_dt.isoformat(),
                    "scheduled": True,
                })
            else:
                item.update({"hours_until": None, "scheduled": False})
            pending_assessments.append(item)
        # 面试中：全部列出，与看板「面试中」列一致
        if a.status == "interview":
            item = _to_dict(a)
            if a.next_interview_at:
                interview_dt = a.next_interview_at
                if interview_dt.tzinfo is None:
                    interview_dt = interview_dt.replace(tzinfo=timezone.utc)
                delta = interview_dt - now
                hours = delta.total_seconds() / 3600
                item.update({
                    "hours_until": round(hours, 1),
                    "when": interview_dt.isoformat(),
                    "scheduled": True,
                })
            else:
                item.update({"hours_until": None, "scheduled": False})
            upcoming.append(item)
        # 待回复 offer：未填写或 pending 均视为待回复
        if a.status == "offer" and (a.offer_status or "pending") not in ("accepted", "declined"):
            pending_offers.append(_to_dict(a))

    # 排序：有时间倒计时升序在前，未安排时间的垫底
    def _by_hours(x):
        h = x.get("hours_until")
        return (1, 0) if h is None else (0, h)

    stale_apps.sort(key=lambda x: -x["stale_days"])
    pending_assessments.sort(key=_by_hours)
    upcoming.sort(key=_by_hours)

    return ok({
        "stale": stale_apps,
        "pending_assessments": pending_assessments,
        "upcoming_interviews": upcoming,
        "pending_offers": pending_offers,
        "total_alerts": len(stale_apps) + len(pending_assessments) + len(upcoming) + len(pending_offers),
    }, message="获取跟进提醒成功")
