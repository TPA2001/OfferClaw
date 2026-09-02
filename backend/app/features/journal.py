"""
求职日志 Feature

记录求职过程中的笔记、面试复盘、情绪状态。
借鉴 CareerDesk 的 journal 模块。

能力：
- 创建/查询/更新日志条目
- 面试复盘（LLM 辅助分析）
- 情绪追踪（求职状态自查）
- 周报/月报生成
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, String, Text, JSON
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.llm import LLMProvider, LLMResponse, Message

logger = logging.getLogger("offercabin.features.journal")


class JournalEntry(Base):
    """求职日志表"""
    __tablename__ = "journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=False, index=True)

    # 日志类型：note/interview_review/mood_check/weekly_summary
    entry_type = Column(String(30), nullable=False, index=True)

    # 关联的投递记录（可选）
    application_id = Column(String(36), nullable=True, index=True)

    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)

    # 结构化数据（如面试复盘的问题/答案/评分）
    # 注意：属性名不能用 'metadata'（SQLAlchemy Declarative 保留字），用 'meta'，DB 列名仍为 'metadata'
    meta = Column("metadata", JSON, nullable=True, default=dict)

    # 情绪状态（1-5，仅 mood_check 类型使用）
    mood_score = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class JournalService:
    """求职日志服务"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def _chat(self, system: str, user: str, temperature: float = 0.6) -> str:
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]
        resp: LLMResponse = await self.llm.chat(messages, temperature=temperature)
        return resp.content or ""

    async def review_interview(
        self,
        interview_notes: str,
        position: Optional[str] = None,
        company: Optional[str] = None,
    ) -> dict:
        """
        LLM 辅助面试复盘。

        Args:
            interview_notes: 面试笔记（被问了什么/怎么答的/感受）
            position: 岗位
            company: 公司

        Returns:
            {
                "performance": "表现总评",
                "strengths": ["做得好的地方"],
                "weaknesses": ["需要改进"],
                "key_questions": [{"q": "问题", "your_answer": "你的回答", "better_answer": "更好的回答"}],
                "action_items": ["行动项1"],
                "mood": "情绪评估"
            }
        """
        system = (
            "你是面试复盘教练。帮助候选人分析面试表现，给出可操作的改进建议。\n"
            "态度要温和但诚实，不回避问题。\n\n"
            "输出 JSON：\n"
            "{\n"
            '  "performance": "整体表现评价（2-3句）",\n'
            '  "strengths": ["做得好的1", "做得好的2"],\n'
            '  "weaknesses": ["需要改进的1"],\n'
            '  "key_questions": [{"q":"问题", "your_answer":"你的回答摘要", "better_answer":"更好的回答"}],\n'
            '  "action_items": ["行动项1"],\n'
            '  "mood": "情绪状态评估"\n'
            "}\n只输出 JSON。"
        )

        user_parts = []
        if company:
            user_parts.append(f"公司：{company}")
        if position:
            user_parts.append(f"岗位：{position}")
        user_parts.append(f"面试笔记：\n{interview_notes}")

        user = "\n".join(user_parts)

        try:
            raw = await self._chat(system, user, temperature=0.4)
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"面试复盘失败: {e}")

        return {
            "performance": "复盘服务暂时不可用",
            "strengths": [],
            "weaknesses": [],
            "key_questions": [],
            "action_items": [],
            "mood": "未知",
        }

    async def generate_weekly_summary(
        self,
        user_id: str,
        db,
        week_start: Optional[datetime] = None,
    ) -> dict:
        """
        生成求职周报：本周投递/面试/复盘/情绪趋势。
        """
        from sqlalchemy import select, and_

        if week_start is None:
            week_start = datetime.now(timezone.utc)

        # 查询本周日志
        stmt = select(JournalEntry).where(
            and_(
                JournalEntry.user_id == user_id,
                JournalEntry.created_at >= week_start,
            )
        )
        entries = db.execute(stmt).scalars().all()

        # 查询本周投递
        from app.models.application import Application
        app_stmt = select(Application).where(
            and_(
                Application.user_id == user_id,
                Application.applied_at >= week_start,
            )
        )
        apps = db.execute(app_stmt).scalars().all()

        summary_input = (
            f"本周投递 {len(apps)} 个岗位，"
            f"记录 {len(entries)} 条日志。\n"
            f"投递公司：{', '.join(a.company for a in apps[:10])}\n"
            f"日志摘要：{'; '.join(e.title or e.entry_type for e in entries[:10])}"
        )

        system = (
            "你是求职教练。基于本周数据生成求职周报。\n"
            "输出 JSON：\n"
            "{\n"
            '  "highlight": "本周亮点",\n'
            '  "stats": {"applications": 0, "interviews": 0, "rejections": 0},\n'
            '  "mood_trend": "情绪趋势",\n'
            '  "next_week_focus": ["下周重点1"],\n'
            '  "encouragement": "鼓励的话"\n'
            "}\n只输出 JSON。"
        )

        try:
            raw = await self._chat(system, summary_input, temperature=0.5)
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"周报生成失败: {e}")

        return {
            "highlight": "本周周报生成服务暂时不可用",
            "stats": {"applications": len(apps), "interviews": 0, "rejections": 0},
            "next_week_focus": [],
            "encouragement": "继续加油！",
        }


# ===== 公共边界 =====
_service: Optional[JournalService] = None


def get_journal_service(llm: Optional[LLMProvider] = None) -> JournalService:
    """获取日志服务单例"""
    global _service
    if _service is None or llm is not None:
        from app.core.llm import get_gen_provider
        _llm = llm or get_gen_provider()
        _service = JournalService(_llm)
    return _service
