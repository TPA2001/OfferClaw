"""
看板统计工具
"""

from typing import Optional
from datetime import datetime, timezone
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import func

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


class GetDashboardStatsTool(BaseTool):
    """获取投递看板统计数据"""

    name = "get_dashboard_stats"
    description = "获取用户投递看板的统计概览，包括各状态数量、回复率、offer率、平均等待天数。当用户问'我的投递情况'、'给我看下统计'、'我的offer率怎么样'时调用。"
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

        if not apps:
            return ToolResult(success=True, data={
                "message": "你还没有任何投递记录",
                "total": 0,
            })

        total = len(apps)
        status_counter = Counter(a.status for a in apps)
        offer_count = status_counter.get("offer", 0)
        rejected_count = status_counter.get("rejected", 0)
        # 回复率 = (offer + rejected + interview + assessment) / total
        replied = sum(status_counter.get(s, 0) for s in ["assessment", "interview", "offer", "rejected"])
        reply_rate = replied / total if total else 0
        offer_rate = offer_count / total if total else 0

        # 平均等待天数（applied_at 到 now，对于未结束的）
        now = datetime.now(timezone.utc)
        waiting_days = []
        for a in apps:
            if a.applied_at and a.status not in ["offer", "rejected", "withdrawn"]:
                if a.applied_at.tzinfo is None:
                    applied = a.applied_at.replace(tzinfo=timezone.utc)
                else:
                    applied = a.applied_at
                days = (now - applied).days
                if days >= 0:
                    waiting_days.append(days)
        avg_wait = sum(waiting_days) / len(waiting_days) if waiting_days else 0

        return ToolResult(success=True, data={
            "total": total,
            "by_status": {STATUS_LABELS.get(k, k): v for k, v in status_counter.items()},
            "offer_count": offer_count,
            "rejected_count": rejected_count,
            "reply_rate": f"{reply_rate * 100:.1f}%",
            "offer_rate": f"{offer_rate * 100:.1f}%",
            "avg_wait_days": round(avg_wait, 1),
            "waiting_count": len(waiting_days),
        })
