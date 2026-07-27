"""
投递记录相关工具
"""

import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.application import Application
from ..runtime.base_tool import BaseTool, ToolResult


# 合法状态枚举
VALID_STATUSES = {
    "applied": "已投递",
    "assessment": "笔试中",
    "interview": "面试中",
    "offer": "已录用",
    "rejected": "已拒绝",
    "withdrawn": "已撤回",
}

REJECTION_STAGES = {
    "resume_rejected": "简历初筛挂",
    "assessment_failed": "笔试挂",
    "interview_1_failed": "一面挂",
    "interview_2_failed": "二面挂",
    "interview_3_failed": "三面挂",
    "hr_failed": "HR面挂",
    "offer_collapsed": "offer谈崩",
    "hc_empty": "HC没有",
    "other": "其他",
}

OFFER_STATUSES = {
    "pending": "待回复",
    "accepted": "已接受",
    "declined": "已拒绝offer",
}

PRIORITIES = {"high": "心仪", "medium": "普通", "low": "备选"}


def _parse_dt(val: Optional[str]):
    """ISO 字符串 → datetime，容错"""
    if not val:
        return None
    try:
        if isinstance(val, datetime):
            return val
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _append_history(app: Application, old: Optional[str], new: str, note: Optional[str] = None):
    """追加状态变更历史"""
    history = list(app.status_history or [])
    history.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "from": old,
        "to": new,
        "note": note,
    })
    app.status_history = history


class CreateApplicationTool(BaseTool):
    """创建投递记录"""

    name = "create_application"
    description = (
        "创建一条投递记录。当用户说'记录我投递了XX公司的XX岗位'、'我投了腾讯后端'等场景调用。"
        "可同时记录来源、优先级、标签。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "公司名称"},
            "position": {"type": "string", "description": "岗位名称"},
            "job_url": {"type": "string", "description": "职位链接（可选）"},
            "source": {"type": "string", "description": "投递来源：boss/直聘/官网/内推/校招（可选）"},
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "优先级：high=心仪必拿/medium=普通/low=备选（可选，默认 medium）",
            },
            "notes": {"type": "string", "description": "备注（可选）"},
            "tags": {"type": "string", "description": "标签，逗号分隔（可选）"},
        },
        "required": ["company", "position"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        company: str,
        position: str,
        job_url: Optional[str] = None,
        source: Optional[str] = None,
        priority: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> ToolResult:
        # 重复投递检测（30 天内同公司同岗位）
        from datetime import timedelta
        dup_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        existing = self.db.query(Application).filter(
            Application.user_id == self.user_id,
            Application.company == company,
            Application.position == position,
            Application.status != "withdrawn",
            or_(Application.applied_at >= dup_threshold, Application.applied_at.is_(None)),
        ).first()

        app = Application(
            id=str(uuid.uuid4()),
            user_id=self.user_id,
            company=company,
            position=position,
            job_url=job_url,
            source=source,
            notes=notes,
            tags=tags,
            status="applied",
            priority=priority or "medium",
        )
        # 初始状态历史
        _append_history(app, None, "applied", "创建投递记录")
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)

        data = {
            "message": f"已记录投递：{company} - {position}",
            "application_id": str(app.id),
            "status": "applied",
        }
        if existing:
            data["warning"] = (
                f"30 天内已投递过 {company} - {position}（当前状态：{VALID_STATUSES.get(existing.status)}），"
                f"请确认是否重复投递"
            )
        return ToolResult(success=True, data=data)


class UpdateApplicationTool(BaseTool):
    """更新投递记录（支持所有细化字段）"""

    name = "update_application"
    description = (
        "更新投递记录，支持状态流转和所有细化字段。这是核心工具，能一次性更新多个字段。\n"
        "场景示例：\n"
        "- '我收到腾讯的笔试通知了，下周三截止' → status=assessment, assessment_deadline=...\n"
        "- '我明天下午2点去字节二面' → status=interview, interview_round=2, next_interview_at=...\n"
        "- '我拿到阿里offer了，25k×16，base杭州，下周三前答复' → status=offer, offer_status=pending, offer_salary=25k×16, offer_location=杭州, offer_deadline=...\n"
        "- '美团二面挂了' → status=rejected, rejection_stage=interview_2_failed\n"
        "- '把腾讯标记为心仪公司' → priority=high\n"
        "定位方式：application_id（优先）或 company（模糊匹配，唯一时自动定位）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "application_id": {"type": "string", "description": "投递记录 ID（优先使用）"},
            "company": {"type": "string", "description": "公司名称（用于定位记录，模糊匹配）"},
            "status": {
                "type": "string",
                "enum": list(VALID_STATUSES.keys()),
                "description": "新状态（可选）",
            },
            "rejection_stage": {
                "type": "string",
                "enum": list(REJECTION_STAGES.keys()),
                "description": "拒绝环节（仅 status=rejected 时使用）",
            },
            "interview_round": {
                "type": "integer",
                "description": "当前面试轮次：1=一面 2=二面 3=三面 4=HR面（仅 status=interview）",
            },
            "next_interview_at": {
                "type": "string",
                "description": "下一面试时间，ISO 格式如 2026-07-25T14:00:00（仅 status=interview）",
            },
            "assessment_deadline": {
                "type": "string",
                "description": "笔试截止时间，ISO 格式（仅 status=assessment）",
            },
            "offer_status": {
                "type": "string",
                "enum": list(OFFER_STATUSES.keys()),
                "description": "offer 状态：pending/accepted/declined（仅 status=offer）",
            },
            "offer_salary": {"type": "string", "description": "薪资，如 25k×16 或 30-35k"},
            "offer_location": {"type": "string", "description": "工作地点"},
            "offer_deadline": {
                "type": "string",
                "description": "签约最后期限，ISO 格式",
            },
            "hr_contact": {"type": "string", "description": "HR 联系方式（微信/电话/邮箱）"},
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "优先级（可选）",
            },
            "notes": {"type": "string", "description": "追加备注（追加到末尾，不覆盖）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        application_id: Optional[str] = None,
        company: Optional[str] = None,
        status: Optional[str] = None,
        rejection_stage: Optional[str] = None,
        interview_round: Optional[int] = None,
        next_interview_at: Optional[str] = None,
        assessment_deadline: Optional[str] = None,
        offer_status: Optional[str] = None,
        offer_salary: Optional[str] = None,
        offer_location: Optional[str] = None,
        offer_deadline: Optional[str] = None,
        hr_contact: Optional[str] = None,
        priority: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ToolResult:
        # 校验枚举值
        if status and status not in VALID_STATUSES:
            return ToolResult(success=False, error=f"非法状态: {status}")
        if rejection_stage and rejection_stage not in REJECTION_STAGES:
            return ToolResult(success=False, error=f"非法拒绝环节: {rejection_stage}")
        if offer_status and offer_status not in OFFER_STATUSES:
            return ToolResult(success=False, error=f"非法 offer 状态: {offer_status}")
        if priority and priority not in PRIORITIES:
            return ToolResult(success=False, error=f"非法优先级: {priority}")

        # 定位记录
        app = None
        if application_id:
            app = self.db.query(Application).filter(
                Application.id == application_id,
                Application.user_id == self.user_id,
            ).first()
            if not app:
                return ToolResult(success=False, error=f"未找到 application_id={application_id}")
        elif company:
            apps = self.db.query(Application).filter(
                Application.user_id == self.user_id,
                Application.company.like(f"%{company}%"),
            ).order_by(Application.updated_at.desc().nullslast()).all()
            if not apps:
                return ToolResult(success=False, error=f"未找到公司含 '{company}' 的记录")
            if len(apps) > 1:
                return ToolResult(success=False, data={
                    "message": f"找到 {len(apps)} 条匹配，请指定 application_id",
                    "candidates": [
                        {"id": str(a.id), "company": a.company, "position": a.position, "status": a.status}
                        for a in apps[:5]
                    ],
                })
            app = apps[0]

        if not app:
            return ToolResult(success=False, error="未指定 application_id 或 company，无法定位")

        old_status = app.status
        updated = []

        # 状态变更 + 联动清理
        if status and status != old_status:
            app.status = status
            updated.append(f"状态: {VALID_STATUSES.get(old_status, old_status)}→{VALID_STATUSES[status]}")
            # 清理不相关字段
            if status != "rejected":
                app.rejection_stage = None
            if status != "interview":
                app.interview_round = None
                app.next_interview_at = None
            if status != "assessment":
                app.assessment_deadline = None
            if status != "offer":
                app.offer_status = None
                app.offer_salary = None
                app.offer_location = None
                app.offer_deadline = None

        # 细化字段
        if rejection_stage:
            app.rejection_stage = rejection_stage
            updated.append(f"拒绝环节: {REJECTION_STAGES[rejection_stage]}")
        if interview_round is not None:
            app.interview_round = interview_round
            updated.append(f"面试轮次: {interview_round}")
        if next_interview_at:
            app.next_interview_at = _parse_dt(next_interview_at)
            updated.append(f"面试时间: {next_interview_at}")
        if assessment_deadline:
            app.assessment_deadline = _parse_dt(assessment_deadline)
            updated.append(f"笔试截止: {assessment_deadline}")
        if offer_status:
            app.offer_status = offer_status
            updated.append(f"offer状态: {OFFER_STATUSES[offer_status]}")
        if offer_salary:
            app.offer_salary = offer_salary
            updated.append(f"薪资: {offer_salary}")
        if offer_location:
            app.offer_location = offer_location
            updated.append(f"地点: {offer_location}")
        if offer_deadline:
            app.offer_deadline = _parse_dt(offer_deadline)
            updated.append(f"签约截止: {offer_deadline}")
        if hr_contact:
            app.hr_contact = hr_contact
            updated.append(f"HR联系方式: {hr_contact}")
        if priority:
            app.priority = priority
            updated.append(f"优先级: {PRIORITIES[priority]}")
        if notes:
            existing = app.notes or ""
            app.notes = f"{existing}\n[更新] {notes}" if existing else f"[更新] {notes}"
            updated.append("备注已追加")

        # 状态变更历史
        if status and status != old_status:
            _append_history(app, old_status, status, notes)

        self.db.commit()
        self.db.refresh(app)
        return ToolResult(success=True, data={
            "message": f"已更新 {app.company} - {app.position}：" + "，".join(updated) if updated else "无变更",
            "application_id": str(app.id),
            "updated_fields": updated,
            "current_status": app.status,
        })


# 保留旧名称做兼容（job_agent 可逐步迁移）
UpdateApplicationStatusTool = UpdateApplicationTool


class QueryApplicationsTool(BaseTool):
    """查询投递记录"""

    name = "query_applications"
    description = (
        "查询用户的投递记录列表。可按状态、公司名过滤。"
        "当用户问'我有哪些投递'、'查看我的投递记录'、'面试中的岗位有哪些'时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": list(VALID_STATUSES.keys()),
                "description": "按状态过滤（可选）",
            },
            "company": {"type": "string", "description": "按公司名过滤（可选，模糊匹配）"},
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "按优先级过滤（可选）",
            },
            "limit": {"type": "integer", "description": "返回数量上限，默认 20", "default": 20},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        status: Optional[str] = None,
        company: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> ToolResult:
        q = self.db.query(Application).filter(Application.user_id == self.user_id)
        if status:
            if status not in VALID_STATUSES:
                return ToolResult(success=False, error=f"非法状态: {status}")
            q = q.filter(Application.status == status)
        if company:
            q = q.filter(Application.company.like(f"%{company}%"))
        if priority:
            q = q.filter(Application.priority == priority)
        apps = q.order_by(
            Application.priority.asc(),
            Application.updated_at.desc().nullslast(),
        ).limit(limit).all()

        if not apps:
            return ToolResult(success=True, data={
                "message": "未找到符合条件的投递记录",
                "applications": [],
                "count": 0,
            })

        return ToolResult(success=True, data={
            "applications": [
                {
                    "id": str(a.id),
                    "company": a.company,
                    "position": a.position,
                    "status": a.status,
                    "status_label": VALID_STATUSES.get(a.status, a.status),
                    "priority": a.priority or "medium",
                    "source": a.source,
                    "interview_round": a.interview_round,
                    "next_interview_at": a.next_interview_at.isoformat() if a.next_interview_at else None,
                    "assessment_deadline": a.assessment_deadline.isoformat() if a.assessment_deadline else None,
                    "offer_salary": a.offer_salary,
                    "offer_status": a.offer_status,
                    "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                    "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                    "notes": a.notes,
                    "tags": a.tags,
                    "job_url": a.job_url,
                }
                for a in apps
            ],
            "count": len(apps),
        })


class DeleteApplicationTool(BaseTool):
    """删除投递记录（需确认）"""

    name = "delete_application"
    description = "删除一条投递记录。属于敏感操作，会要求用户确认。可通过 application_id 或 company 定位。"
    parameters = {
        "type": "object",
        "properties": {
            "application_id": {"type": "string", "description": "投递记录 ID"},
            "company": {"type": "string", "description": "公司名（用于定位，可选）"},
        },
        "required": ["application_id"],
    }
    requires_confirmation = True

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        application_id: str,
        company: Optional[str] = None,
    ) -> ToolResult:
        app = self.db.query(Application).filter(
            Application.id == application_id,
            Application.user_id == self.user_id,
        ).first()

        if not app:
            return ToolResult(success=False, error=f"未找到 application_id={application_id} 的记录")

        info = {"company": app.company, "position": app.position, "id": str(app.id)}
        self.db.delete(app)
        self.db.commit()
        return ToolResult(success=True, data={
            "message": f"已删除投递记录：{info['company']} - {info['position']}",
            **info,
        })
