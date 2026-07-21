"""
投递记录相关工具
"""

import uuid
from typing import Optional

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


class CreateApplicationTool(BaseTool):
    """创建投递记录"""

    name = "create_application"
    description = "创建一条投递记录。当用户说'记录我投递了XX公司的XX岗位'、'我投了腾讯后端'等场景调用。"
    parameters = {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "公司名称"},
            "position": {"type": "string", "description": "岗位名称"},
            "job_url": {"type": "string", "description": "职位链接（可选）"},
            "source": {"type": "string", "description": "投递来源：boss/直聘/官网/内推/校招（可选）"},
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
        notes: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> ToolResult:
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
        )
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return ToolResult(success=True, data={
            "message": f"已记录投递：{company} - {position}",
            "application_id": str(app.id),
            "status": "applied",
        })


class UpdateApplicationStatusTool(BaseTool):
    """更新投递状态"""

    name = "update_application_status"
    description = "更新某条投递记录的状态。合法状态：applied(已投递)/assessment(笔试中)/interview(面试中)/offer(已录用)/rejected(已拒绝)/withdrawn(已撤回)。可通过 company 名称定位记录。"
    parameters = {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "公司名称（用于定位记录）"},
            "status": {
                "type": "string",
                "enum": list(VALID_STATUSES.keys()),
                "description": "新状态",
            },
            "application_id": {"type": "string", "description": "投递记录 ID（可选，优先使用）"},
            "notes": {"type": "string", "description": "追加备注（可选）"},
        },
        "required": ["status"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        status: str,
        company: Optional[str] = None,
        application_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ToolResult:
        if status not in VALID_STATUSES:
            return ToolResult(
                success=False,
                error=f"非法状态 {status}，合法值: {list(VALID_STATUSES.keys())}",
            )

        # 定位记录
        app = None
        if application_id:
            app = self.db.query(Application).filter(
                Application.id == application_id,
                Application.user_id == self.user_id,
            ).first()
            if not app:
                return ToolResult(success=False, error=f"未找到 application_id={application_id} 的记录")
        elif company:
            # 模糊匹配公司名，按 updated_at 倒序取最近一条
            apps = self.db.query(Application).filter(
                Application.user_id == self.user_id,
                Application.company.like(f"%{company}%"),
            ).order_by(Application.updated_at.desc().nullslast()).all()
            if not apps:
                return ToolResult(success=False, error=f"未找到公司含 '{company}' 的投递记录")
            if len(apps) > 1:
                return ToolResult(success=False, data={
                    "message": f"找到 {len(apps)} 条匹配记录，请指定 application_id",
                    "candidates": [
                        {"id": str(a.id), "company": a.company, "position": a.position, "status": a.status}
                        for a in apps[:5]
                    ],
                })
            app = apps[0]

        if not app:
            return ToolResult(success=False, error="未指定 company 或 application_id，无法定位记录")

        old_status = app.status
        app.status = status
        if notes:
            existing = app.notes or ""
            app.notes = f"{existing}\n[{status}] {notes}" if existing else f"[{status}] {notes}"

        self.db.commit()
        self.db.refresh(app)
        return ToolResult(success=True, data={
            "message": f"{app.company} - {app.position} 状态变更：{VALID_STATUSES.get(old_status, old_status)} → {VALID_STATUSES[status]}",
            "application_id": str(app.id),
            "old_status": old_status,
            "new_status": status,
        })


class QueryApplicationsTool(BaseTool):
    """查询投递记录"""

    name = "query_applications"
    description = "查询用户的投递记录列表。可按状态、公司名过滤。当用户问'我有哪些投递'、'查看我的投递记录'、'面试中的岗位有哪些'时调用。"
    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "按状态过滤（可选）：applied/assessment/interview/offer/rejected/withdrawn",
            },
            "company": {"type": "string", "description": "按公司名过滤（可选，模糊匹配）"},
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
        limit: int = 20,
    ) -> ToolResult:
        q = self.db.query(Application).filter(Application.user_id == self.user_id)
        if status:
            if status not in VALID_STATUSES:
                return ToolResult(success=False, error=f"非法状态: {status}")
            q = q.filter(Application.status == status)
        if company:
            q = q.filter(Application.company.like(f"%{company}%"))
        apps = q.order_by(Application.updated_at.desc().nullslast()).limit(limit).all()

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
                    "source": a.source,
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
