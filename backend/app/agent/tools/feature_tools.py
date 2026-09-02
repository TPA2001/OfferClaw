"""
Feature 工具层

将 features/ 模块的业务能力封装为 agent 可调用的工具。
每个 feature 通过 public.py 暴露的接口被封装为一个或多个工具。

工具列表：
- ResearchCompanyTool: 公司调研（company_research feature）
- GenerateInterviewQuestionsTool: 生成面试题集（mock_interview feature）
- EvaluateInterviewAnswerTool: 评估面试答案（mock_interview feature）
- ReviewInterviewTool: 面试复盘（journal feature）
- CreateJournalEntryTool: 创建日志（journal feature）
- GenerateWeeklySummaryTool: 生成周报（journal feature）

设计原则：
- 工具只通过 feature 的 public 接口访问业务逻辑，不直接操作 repository
- 工具负责参数校验和结果格式化，不包含业务逻辑
- 敏感操作（如删除日志）需要用户确认
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.llm import LLMProvider
from ..runtime.base_tool import BaseTool, ToolResult

logger = logging.getLogger("offercabin.agent.tools.features")


# ====================================================================
# 1. 公司调研工具
# ====================================================================

class ResearchCompanyTool(BaseTool):
    """公司调研：生成公司结构化报告"""

    name = "research_company"
    description = (
        "调研一家公司，生成结构化报告（行业/概况/优势/风险/面试建议/薪资参考）。"
        "当用户说'帮我调研XX公司'、'XX公司怎么样'、'了解一下这家公司'时调用。"
        "可与 verify_job_authenticity 配合：先查真实性，再调研公司详情。"
        "参数：company_name（公司名，必需），job_position（目标岗位，可选），known_info（已知信息，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "company_name": {"type": "string", "description": "公司名称"},
            "job_position": {"type": "string", "description": "目标岗位（可选，用于针对性分析）"},
            "known_info": {"type": "string", "description": "已知信息（可选，如 Boss 搜索结果中的公司简介）"},
        },
        "required": ["company_name"],
    }

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def execute(
        self,
        company_name: str,
        job_position: Optional[str] = None,
        known_info: Optional[str] = None,
    ) -> ToolResult:
        from app.features.company_research import get_company_research_service

        if not company_name or not company_name.strip():
            return ToolResult(success=False, error="公司名称不能为空")

        try:
            service = get_company_research_service(self.llm)
            result = await service.research_company(
                company_name=company_name.strip(),
                job_position=job_position,
                known_info=known_info,
            )

            # 构造易读摘要
            industry = result.get("industry", "未知")
            summary = result.get("summary", "")
            pros = result.get("pros", [])
            cons = result.get("cons", [])

            message_parts = [f"## {company_name} 调研报告\n"]
            message_parts.append(f"**行业**：{industry}\n")
            message_parts.append(f"**概况**：{summary}\n")

            if pros:
                message_parts.append("\n**优势**：")
                for p in pros:
                    message_parts.append(f"- {p}")

            if cons:
                message_parts.append("\n**风险**：")
                for c in cons:
                    message_parts.append(f"- {c}")

            if result.get("interview_tips"):
                message_parts.append("\n**面试建议**：")
                for tip in result["interview_tips"]:
                    message_parts.append(f"- {tip}")

            if result.get("salary_reference"):
                message_parts.append(f"\n**薪资参考**：{result['salary_reference']}")

            return ToolResult(success=True, data={
                "message": "\n".join(message_parts),
                **result,
            })
        except Exception as e:
            logger.error(f"公司调研失败: {e}", exc_info=True)
            return ToolResult(success=False, error=f"公司调研失败: {e}")


# ====================================================================
# 2. 面试题集生成工具
# ====================================================================

class GenerateInterviewQuestionsTool(BaseTool):
    """生成定制面试题集"""

    name = "generate_interview_questions"
    description = (
        "根据 JD 和简历生成定制面试题集，含题目/难度/得分点/参考答案。"
        "当用户说'帮我出几道面试题'、'模拟面试题'、'面试会问什么'时调用。"
        "参数：jd_text（JD文本，必需），profile_text（简历文本，可选），"
        "interview_type（面试类型：technical/behavioral/system_design/hr，默认technical），"
        "count（题目数量，默认10）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "岗位 JD 文本"},
            "profile_text": {"type": "string", "description": "候选人简历文本（可选，用于个性化出题）"},
            "interview_type": {
                "type": "string",
                "enum": ["technical", "behavioral", "system_design", "hr"],
                "description": "面试类型，默认 technical",
            },
            "count": {"type": "integer", "description": "题目数量，默认 10"},
        },
        "required": ["jd_text"],
    }

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def execute(
        self,
        jd_text: str,
        profile_text: Optional[str] = None,
        interview_type: str = "technical",
        count: int = 10,
    ) -> ToolResult:
        from app.features.mock_interview import get_mock_interview_service

        if not jd_text or not jd_text.strip():
            return ToolResult(success=False, error="JD 文本不能为空")

        try:
            service = get_mock_interview_service(self.llm)
            result = await service.generate_questions(
                jd_text=jd_text.strip(),
                profile_text=profile_text,
                interview_type=interview_type,
                count=min(max(count, 1), 20),  # 限制 1-20 题
            )

            questions = result.get("questions", [])
            advice = result.get("advice", "")

            type_label = {
                "technical": "技术面", "behavioral": "行为面",
                "system_design": "系统设计", "hr": "HR面",
            }.get(interview_type, "技术面")

            message_parts = [f"## {type_label}面试题集（共 {len(questions)} 题）\n"]

            for i, q in enumerate(questions, 1):
                difficulty = q.get("difficulty", "medium")
                diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "⚪")
                message_parts.append(f"### {i}. {q.get('q', '?')} {diff_emoji}\n")
                message_parts.append(f"- 类型：{q.get('type', '?')}")
                message_parts.append(f"- 难度：{difficulty}")

                key_points = q.get("key_points", [])
                if key_points:
                    message_parts.append(f"- 得分点：{', '.join(key_points)}")

                if q.get("reference_answer"):
                    message_parts.append(f"\n**参考答案**：\n{q['reference_answer']}")
                message_parts.append("")

            if advice:
                message_parts.append(f"\n**面试建议**：{advice}")

            return ToolResult(success=True, data={
                "message": "\n".join(message_parts),
                **result,
            })
        except Exception as e:
            logger.error(f"生成面试题失败: {e}", exc_info=True)
            return ToolResult(success=False, error=f"生成面试题失败: {e}")


# ====================================================================
# 3. 面试答案评估工具
# ====================================================================

class EvaluateInterviewAnswerTool(BaseTool):
    """评估面试答案"""

    name = "evaluate_interview_answer"
    description = (
        "评估候选人的面试答案，给出分数/覆盖得分点/遗漏点/改进建议/参考答案。"
        "当用户说'帮我看看这个回答怎么样'、'评估一下我的答案'时调用。"
        "参数：question（题目，必需），answer（答案，必需），key_points（得分点列表，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "面试题目"},
            "answer": {"type": "string", "description": "候选人的答案"},
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关键得分点（可选）",
            },
        },
        "required": ["question", "answer"],
    }

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def execute(
        self,
        question: str,
        answer: str,
        key_points: Optional[list[str]] = None,
    ) -> ToolResult:
        from app.features.mock_interview import get_mock_interview_service

        if not question or not answer:
            return ToolResult(success=False, error="题目和答案都不能为空")

        try:
            service = get_mock_interview_service(self.llm)
            result = await service.evaluate_answer(
                question=question.strip(),
                answer=answer.strip(),
                key_points=key_points,
            )

            score = result.get("score", 0)
            score_emoji = "🟢" if score >= 70 else ("🟡" if score >= 50 else "🔴")

            message_parts = [f"## 答案评估 {score_emoji} {score}/100\n"]

            covered = result.get("covered_points", [])
            missed = result.get("missed_points", [])

            if covered:
                message_parts.append("\n**已覆盖**：")
                for p in covered:
                    message_parts.append(f"- ✅ {p}")

            if missed:
                message_parts.append("\n**遗漏点**：")
                for p in missed:
                    message_parts.append(f"- ❌ {p}")

            if result.get("improvement"):
                message_parts.append(f"\n**改进建议**：\n{result['improvement']}")

            if result.get("model_answer"):
                message_parts.append(f"\n**参考答案**：\n{result['model_answer']}")

            return ToolResult(success=True, data={
                "message": "\n".join(message_parts),
                **result,
            })
        except Exception as e:
            logger.error(f"答案评估失败: {e}", exc_info=True)
            return ToolResult(success=False, error=f"答案评估失败: {e}")


# ====================================================================
# 4. 面试复盘工具
# ====================================================================

class ReviewInterviewTool(BaseTool):
    """面试复盘：LLM 辅助分析面试表现"""

    name = "review_interview"
    description = (
        "基于面试笔记进行复盘，分析表现/优势/不足/改进建议/行动项。"
        "当用户说'今天面试完了帮我复盘'、'面试复盘'、'分析一下我的面试'时调用。"
        "参数：interview_notes（面试笔记，必需），position（岗位，可选），company（公司，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "interview_notes": {"type": "string", "description": "面试笔记（被问了什么/怎么答的/感受）"},
            "position": {"type": "string", "description": "岗位（可选）"},
            "company": {"type": "string", "description": "公司（可选）"},
        },
        "required": ["interview_notes"],
    }

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def execute(
        self,
        interview_notes: str,
        position: Optional[str] = None,
        company: Optional[str] = None,
    ) -> ToolResult:
        from app.features.journal import get_journal_service

        if not interview_notes or not interview_notes.strip():
            return ToolResult(success=False, error="面试笔记不能为空")

        try:
            service = get_journal_service(self.llm)
            result = await service.review_interview(
                interview_notes=interview_notes.strip(),
                position=position,
                company=company,
            )

            message_parts = ["## 面试复盘报告\n"]

            if result.get("performance"):
                message_parts.append(f"**整体表现**：{result['performance']}\n")

            if result.get("strengths"):
                message_parts.append("**做得好的**：")
                for s in result["strengths"]:
                    message_parts.append(f"- ✅ {s}")

            if result.get("weaknesses"):
                message_parts.append("\n**需要改进**：")
                for w in result["weaknesses"]:
                    message_parts.append(f"- ❌ {w}")

            key_qs = result.get("key_questions", [])
            if key_qs:
                message_parts.append("\n**关键问题复盘**：")
                for q in key_qs:
                    message_parts.append(f"\n**Q**: {q.get('q', '?')}")
                    message_parts.append(f"- 你的回答：{q.get('your_answer', '?')}")
                    message_parts.append(f"- 更好的回答：{q.get('better_answer', '?')}")

            if result.get("action_items"):
                message_parts.append("\n**行动项**：")
                for item in result["action_items"]:
                    message_parts.append(f"- {item}")

            if result.get("mood"):
                message_parts.append(f"\n**情绪状态**：{result['mood']}")

            return ToolResult(success=True, data={
                "message": "\n".join(message_parts),
                **result,
            })
        except Exception as e:
            logger.error(f"面试复盘失败: {e}", exc_info=True)
            return ToolResult(success=False, error=f"面试复盘失败: {e}")


# ====================================================================
# 5. 创建日志条目工具
# ====================================================================

class CreateJournalEntryTool(BaseTool):
    """创建求职日志条目"""

    name = "create_journal_entry"
    description = (
        "创建求职日志条目（笔记/面试复盘/情绪记录）。"
        "当用户说'记一下今天面试'、'写个笔记'、'记录心情'时调用。"
        "参数：entry_type（类型：note/interview_review/mood_check，必需），"
        "content（内容，必需），title（标题，可选），application_id（关联投递ID，可选），"
        "mood_score（情绪分数1-5，仅 mood_check 类型）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "entry_type": {
                "type": "string",
                "enum": ["note", "interview_review", "mood_check"],
                "description": "日志类型",
            },
            "content": {"type": "string", "description": "日志内容"},
            "title": {"type": "string", "description": "标题（可选）"},
            "application_id": {"type": "string", "description": "关联的投递记录ID（可选）"},
            "mood_score": {"type": "string", "description": "情绪分数 1-5（仅 mood_check 类型）"},
        },
        "required": ["entry_type", "content"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        entry_type: str,
        content: str,
        title: Optional[str] = None,
        application_id: Optional[str] = None,
        mood_score: Optional[str] = None,
    ) -> ToolResult:
        from app.features.journal import JournalEntry

        if not content or not content.strip():
            return ToolResult(success=False, error="日志内容不能为空")

        if entry_type not in ("note", "interview_review", "mood_check"):
            return ToolResult(success=False, error=f"无效的日志类型: {entry_type}")

        try:
            entry = JournalEntry(
                user_id=self.user_id,
                entry_type=entry_type,
                content=content.strip(),
                title=title,
                application_id=application_id,
                mood_score=mood_score if entry_type == "mood_check" else None,
            )
            self.db.add(entry)
            self.db.commit()
            self.db.refresh(entry)

            type_label = {
                "note": "笔记", "interview_review": "面试复盘", "mood_check": "情绪记录",
            }.get(entry_type, entry_type)

            return ToolResult(success=True, data={
                "message": f"已创建{type_label}：{title or '无标题'}",
                "entry_id": entry.id,
                "entry_type": entry_type,
                "title": title,
            })
        except Exception as e:
            logger.error(f"创建日志失败: {e}", exc_info=True)
            self.db.rollback()
            return ToolResult(success=False, error=f"创建日志失败: {e}")


# ====================================================================
# 6. 求职周报工具
# ====================================================================

class GenerateWeeklySummaryTool(BaseTool):
    """生成求职周报"""

    name = "generate_weekly_summary"
    description = (
        "生成本周求职周报：投递统计/面试情况/情绪趋势/下周重点。"
        "当用户说'帮我生成本周周报'、'这周求职总结'、'周报'时调用。"
        "无需参数，自动查询本周数据。"
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(self) -> ToolResult:
        from app.features.journal import get_journal_service

        try:
            service = get_journal_service(self.llm)
            result = await service.generate_weekly_summary(
                user_id=self.user_id,
                db=self.db,
            )

            message_parts = ["## 求职周报\n"]

            if result.get("highlight"):
                message_parts.append(f"**本周亮点**：{result['highlight']}\n")

            stats = result.get("stats", {})
            if stats:
                message_parts.append("**数据统计**：")
                message_parts.append(f"- 投递数：{stats.get('applications', 0)}")
                message_parts.append(f"- 面试数：{stats.get('interviews', 0)}")
                message_parts.append(f"- 拒绝数：{stats.get('rejections', 0)}")

            if result.get("mood_trend"):
                message_parts.append(f"\n**情绪趋势**：{result['mood_trend']}")

            if result.get("next_week_focus"):
                message_parts.append("\n**下周重点**：")
                for focus in result["next_week_focus"]:
                    message_parts.append(f"- {focus}")

            if result.get("encouragement"):
                message_parts.append(f"\n**寄语**：{result['encouragement']}")

            return ToolResult(success=True, data={
                "message": "\n".join(message_parts),
                **result,
            })
        except Exception as e:
            logger.error(f"周报生成失败: {e}", exc_info=True)
            return ToolResult(success=False, error=f"周报生成失败: {e}")
