"""
跟进提醒与统计工具

基于真实校招/社招求职场景：
- 用户登录后最关心：今天有什么要关注的（面试/笔试/offer deadline/长期未回复）
- 复盘时关心：投递趋势、公司维度表现
"""

from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.application import Application
from ..runtime.base_tool import BaseTool, ToolResult


STATUS_LABELS = {
    "applied": "已投递",
    "assessment": "笔试中",
    "interview": "面试中",
    "offer": "已录用",
    "rejected": "已拒绝",
    "withdrawn": "已撤回",
}

INTERVIEW_ROUND_LABELS = {1: "一面", 2: "二面", 3: "三面", 4: "HR面"}


def _to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """确保 datetime 带时区"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class GetFollowupsTool(BaseTool):
    """获取今日跟进提醒"""

    name = "get_followups"
    description = (
        "获取用户需要跟进的事项，按紧急程度分类。这是用户每天打开应用最该看的信息。\n"
        "分类：\n"
        "- upcoming_interviews: 近 3 天内的面试\n"
        "- assessment_deadlines: 笔试 deadline（已过期标红）\n"
        "- offer_deadlines: 待回复的 offer（签约 deadline 临近）\n"
        "- stale_applications: 超过 7 天未回复的投递（建议主动跟进或标记拒绝）\n"
        "当用户问'今天有什么要关注的'、'有什么需要跟进的'、'我的待办'时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self) -> ToolResult:
        now = datetime.now(timezone.utc)
        three_days_later = now + timedelta(days=3)
        seven_days_ago = now - timedelta(days=7)

        apps = self.db.query(Application).filter(
            Application.user_id == self.user_id,
            Application.status.notin_(["withdrawn"]),
        ).all()

        upcoming_interviews = []
        assessment_deadlines = []
        offer_deadlines = []
        stale_applications = []

        for a in apps:
            # 近 3 天面试
            if a.status == "interview" and a.next_interview_at:
                iv = _to_aware(a.next_interview_at)
                if iv and now <= iv <= three_days_later:
                    upcoming_interviews.append({
                        "id": str(a.id),
                        "company": a.company,
                        "position": a.position,
                        "interview_round": a.interview_round,
                        "interview_round_label": INTERVIEW_ROUND_LABELS.get(a.interview_round, str(a.interview_round)),
                        "next_interview_at": iv.isoformat(),
                        "hours_until": round((iv - now).total_seconds() / 3600, 1),
                    })

            # 笔试 deadline
            if a.status == "assessment" and a.assessment_deadline:
                dl = _to_aware(a.assessment_deadline)
                if dl:
                    assessment_deadlines.append({
                        "id": str(a.id),
                        "company": a.company,
                        "position": a.position,
                        "assessment_deadline": dl.isoformat(),
                        "hours_until": round((dl - now).total_seconds() / 3600, 1),
                        "overdue": dl < now,
                    })

            # offer deadline（待回复的）
            if a.status == "offer" and a.offer_status == "pending" and a.offer_deadline:
                dl = _to_aware(a.offer_deadline)
                if dl:
                    offer_deadlines.append({
                        "id": str(a.id),
                        "company": a.company,
                        "position": a.position,
                        "offer_salary": a.offer_salary,
                        "offer_deadline": dl.isoformat(),
                        "hours_until": round((dl - now).total_seconds() / 3600, 1),
                        "overdue": dl < now,
                    })

            # 超过 7 天未回复的投递（仅 applied 状态）
            if a.status == "applied" and a.applied_at:
                applied = _to_aware(a.applied_at)
                if applied and applied < seven_days_ago:
                    days = (now - applied).days
                    stale_applications.append({
                        "id": str(a.id),
                        "company": a.company,
                        "position": a.position,
                        "applied_at": applied.isoformat(),
                        "days_since": days,
                        "priority": a.priority or "medium",
                    })

        # 排序：紧急的在前
        upcoming_interviews.sort(key=lambda x: x["hours_until"])
        assessment_deadlines.sort(key=lambda x: x["hours_until"])
        offer_deadlines.sort(key=lambda x: x["hours_until"])
        stale_applications.sort(key=lambda x: -x["days_since"])

        total = (
            len(upcoming_interviews)
            + len(assessment_deadlines)
            + len(offer_deadlines)
            + len(stale_applications)
        )

        # 生成摘要供 agent 直接引用
        summary_parts = []
        if upcoming_interviews:
            summary_parts.append(f"{len(upcoming_interviews)}场面试即将到来")
        if assessment_deadlines:
            overdue_n = sum(1 for d in assessment_deadlines if d["overdue"])
            summary_parts.append(f"{len(assessment_deadlines)}个笔试deadline" + (f"（{overdue_n}个已过期）" if overdue_n else ""))
        if offer_deadlines:
            summary_parts.append(f"{len(offer_deadlines)}个offer待回复")
        if stale_applications:
            summary_parts.append(f"{len(stale_applications)}个投递超7天未回复")
        summary = "、".join(summary_parts) if summary_parts else "暂无需要跟进的事项"

        return ToolResult(success=True, data={
            "summary": summary,
            "total": total,
            "upcoming_interviews": upcoming_interviews,
            "assessment_deadlines": assessment_deadlines,
            "offer_deadlines": offer_deadlines,
            "stale_applications": stale_applications,
        })


class SearchApplicationsTool(BaseTool):
    """全文搜索投递记录"""

    name = "search_applications"
    description = (
        "全文搜索投递记录（公司/职位/备注/标签）。"
        "当用户问'我投过XX公司吗'、'找一下腾讯的投递'、'搜一下Java相关的'时调用。"
        "投递记录变多后必备的定位能力。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键字（匹配公司/职位/备注/标签）"},
            "limit": {"type": "integer", "description": "返回上限，默认 20", "default": 20},
        },
        "required": ["keyword"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, keyword: str, limit: int = 20) -> ToolResult:
        kw = f"%{keyword.strip()}%"
        apps = self.db.query(Application).filter(
            Application.user_id == self.user_id,
            or_(
                Application.company.like(kw),
                Application.position.like(kw),
                Application.notes.like(kw),
                Application.tags.like(kw),
            ),
        ).order_by(Application.updated_at.desc().nullslast()).limit(limit).all()

        return ToolResult(success=True, data={
            "keyword": keyword,
            "count": len(apps),
            "applications": [
                {
                    "id": str(a.id),
                    "company": a.company,
                    "position": a.position,
                    "status": a.status,
                    "status_label": STATUS_LABELS.get(a.status, a.status),
                    "priority": a.priority or "medium",
                    "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                    "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                    "notes": a.notes,
                    "tags": a.tags,
                }
                for a in apps
            ],
        })


class GetTimelineStatsTool(BaseTool):
    """投递时间趋势统计"""

    name = "get_timeline_stats"
    description = (
        "获取近 N 天的投递趋势（按日聚合：投递数/回复数/offer数）。"
        "当用户问'我最近投递频率怎么样'、'我的投递趋势'、'本周投了多少'时调用。"
        "用于复盘求职节奏：是否持续投递、周末是否懈怠。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "统计天数，默认 30，最大 365", "default": 30},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, days: int = 30) -> ToolResult:
        days = max(1, min(days, 365))
        start = datetime.now(timezone.utc) - timedelta(days=days)
        apps = self.db.query(Application).filter(
            Application.user_id == self.user_id,
            Application.applied_at >= start,
        ).all()

        replied_statuses = {"assessment", "interview", "offer", "rejected"}
        daily: dict = {}
        for a in apps:
            applied = _to_aware(a.applied_at)
            if not applied:
                continue
            key = applied.strftime("%Y-%m-%d")
            if key not in daily:
                daily[key] = {"applied": 0, "replied": 0, "offer": 0}
            daily[key]["applied"] += 1
            if a.status in replied_statuses:
                daily[key]["replied"] += 1
            if a.status == "offer":
                daily[key]["offer"] += 1

        # 补全连续日期序列
        timeline = []
        cursor = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        end = datetime.now(timezone.utc).date()
        while cursor <= end:
            key = cursor.strftime("%Y-%m-%d")
            info = daily.get(key, {"applied": 0, "replied": 0, "offer": 0})
            timeline.append({"date": key, **info})
            cursor += timedelta(days=1)

        total_applied = sum(d["applied"] for d in daily.values())
        return ToolResult(success=True, data={
            "days": days,
            "timeline": timeline,
            "total_applied": total_applied,
            "total_replied": sum(d["replied"] for d in daily.values()),
            "total_offer": sum(d["offer"] for d in daily.values()),
            "avg_per_day": round(total_applied / days, 1) if days else 0,
            "reply_rate": f"{(sum(d['replied'] for d in daily.values()) / total_applied * 100):.1f}%" if total_applied else "0%",
        })


class GetCompanyStatsTool(BaseTool):
    """公司维度统计"""

    name = "get_company_stats"
    description = (
        "获取公司维度统计：每家公司的投递数、回复率、offer率、投递的岗位列表。"
        "当用户问'哪些公司回复积极'、'哪些公司石沉大海'、'按公司看看我的投递'时调用。"
        "用于复盘公司维度的求职表现。"
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self) -> ToolResult:
        apps = self.db.query(Application).filter(
            Application.user_id == self.user_id
        ).all()

        replied_statuses = {"assessment", "interview", "offer", "rejected"}
        companies: dict = {}
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
            applied = _to_aware(a.applied_at)
            if applied and (c["latest_at"] is None or applied > c["latest_at"]):
                c["latest_at"] = applied
                c["latest_status"] = a.status

        result = []
        for c in companies.values():
            positions = sorted(c.pop("positions"))
            latest_at = c.pop("latest_at")
            result.append({
                **c,
                "positions": positions,
                "position_count": len(positions),
                "reply_rate": f"{(c['replied'] / c['total'] * 100):.0f}%" if c["total"] else "0%",
                "offer_rate": f"{(c['offer'] / c['total'] * 100):.0f}%" if c["total"] else "0%",
                "latest_status_label": STATUS_LABELS.get(c["latest_status"], c["latest_status"]) if c["latest_status"] else None,
                "latest_at": latest_at.isoformat() if latest_at else None,
            })
        result.sort(key=lambda x: -x["total"])

        return ToolResult(success=True, data={
            "companies": result,
            "total_companies": len(result),
            "best_reply_company": result[0] if result else None,
        })
