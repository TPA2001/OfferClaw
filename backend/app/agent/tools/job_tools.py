"""
求职内容生成工具（投递前准备能力）

吸取 ai-job-search 的优势，补齐 OfferClaw 在"投递前准备"上的短板：
- JD 抓取与结构化
- 岗位匹配评分
- 简历生成
- 求职信生成
- 面试准备包
- 投递策略建议

所有工具复用 ResumeService（封装 LLM 调用）和现有 LLMProvider 抽象层。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.llm import LLMProvider
from app.models.application import Application
from app.models.profile import Profile
from app.services.resume_service import ResumeService
from ..runtime.base_tool import BaseTool, ToolResult

logger = logging.getLogger("offerclaw.agent.tools.job")


def _load_profile(db: Session, user_id: str) -> Optional[dict]:
    """加载用户画像并转为 dict"""
    p = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not p:
        return None
    return {
        "basic_info": p.basic_info or {},
        "education": p.education or [],
        "experience": p.experience or [],
        "skills": p.skills or [],
        "projects": p.projects or [],
        "summary": p.summary or {},
        "certifications": p.certifications or [],
        "job_intent": p.job_intent or {},
    }


# ====================================================================
# 1. JD 抓取与结构化
# ====================================================================

class ExtractJobDescriptionTool(BaseTool):
    """从 URL 抓取岗位 JD 并结构化"""

    name = "extract_job_description"
    description = (
        "从招聘网页 URL 抓取岗位 JD，返回结构化信息（岗位名/公司/地点/任职要求/岗位职责/技能/薪资）。"
        "当用户说'分析这个岗位 https://...'、'看看这个JD'、'这个岗位要求什么'时调用。"
        "注意：会启动无头浏览器抓取页面，耗时 10-30 秒。抓取结果可用于后续的匹配评分/简历生成/面试准备。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "招聘页面 URL"},
        },
        "required": ["url"],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(self, url: str) -> ToolResult:
        service = ResumeService(self.llm)
        try:
            data = await service.extract_jd_from_url(url)
            if data.get("error"):
                return ToolResult(success=False, error=data["error"], data=data)
            title = data.get("title", "")
            company = data.get("company", "")
            req_count = len(data.get("requirements", []))
            return ToolResult(success=True, data={
                "message": f"已抓取岗位：{company} - {title}（提取到 {req_count} 条要求）",
                **data,
            })
        except Exception as e:
            logger.error(f"JD 抓取失败: {e}")
            return ToolResult(success=False, error=f"JD 抓取失败: {e}")


# ====================================================================
# 2. 岗位匹配评分
# ====================================================================

class ScoreJobMatchTool(BaseTool):
    """评估用户画像与岗位 JD 的匹配度"""

    name = "score_job_match"
    description = (
        "评估用户画像与岗位 JD 的匹配度，返回综合评分（0-100）、5 维度评分、优势、差距、是否建议投递。"
        "评分维度：硬性条件(30%)/技能(25%)/经历(15%)/潜力(15%)/稳定性(15%)，硬性不符会一票否决。"
        "当用户说'这个岗位我合适吗'、'评估一下匹配度'、'要不要投这个'时调用。"
        "参数：jd_text（JD 文本，优先）或 jd_url（JD 链接，自动抓取）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "岗位 JD 文本（优先使用，可从 extract_job_description 结果拼接）"},
            "jd_url": {"type": "string", "description": "岗位 JD 链接（当无 jd_text 时自动抓取）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(
        self,
        jd_text: Optional[str] = None,
        jd_url: Optional[str] = None,
    ) -> ToolResult:
        # 获取 JD 内容
        jd = jd_text
        if not jd and jd_url:
            service = ResumeService(self.llm)
            try:
                data = await service.extract_jd_from_url(jd_url)
                jd = data.get("raw_text") or _jd_to_text(data)
                if not jd:
                    return ToolResult(success=False, error="从 URL 抓取 JD 失败")
            except Exception as e:
                return ToolResult(success=False, error=f"JD 抓取失败: {e}")
        if not jd:
            return ToolResult(success=False, error="请提供 jd_text 或 jd_url")

        # 加载画像
        profile = _load_profile(self.db, self.user_id)
        if not profile:
            return ToolResult(success=False, error="用户尚未创建画像，无法评分。请先在'个人画像'页填写信息。")

        service = ResumeService(self.llm)
        try:
            result = await service.score_job_match(profile, jd)
            score = result.get("score", 0)
            level = result.get("level", "未知")
            veto = result.get("veto", False)
            verdict = "🚫 不建议投递（硬性条件不符）" if veto else (
                f"✅ 建议投递（{level}，{score}分）" if score >= 70 else
                f"⚠️ 谨慎投递（{level}，{score}分）"
            )
            return ToolResult(success=True, data={
                "message": f"匹配评分：{score}/100（{level}）\n{verdict}",
                "verdict": verdict,
                **result,
            })
        except Exception as e:
            logger.error(f"匹配评分失败: {e}")
            return ToolResult(success=False, error=f"评分失败: {e}")


# ====================================================================
# 3. 简历生成
# ====================================================================

class GenerateResumeTool(BaseTool):
    """根据画像 + JD 生成定制化简历"""

    name = "generate_resume"
    description = (
        "根据用户画像生成 Markdown 简历。若提供目标 JD，会针对 JD 重点强调匹配技能和经历。"
        "包含：基本信息/教育/工作/项目/技能/自我评价，自我评价针对 JD 定制。"
        "当用户说'帮我写简历'、'根据这个岗位生成简历'、'定制一份简历'时调用。"
        "参数：jd_text（目标 JD 文本，可选，用于定制）或 jd_url（JD 链接，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "目标岗位 JD 文本（可选，用于针对性定制简历）"},
            "jd_url": {"type": "string", "description": "目标岗位 JD 链接（可选，自动抓取）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(
        self,
        jd_text: Optional[str] = None,
        jd_url: Optional[str] = None,
    ) -> ToolResult:
        profile = _load_profile(self.db, self.user_id)
        if not profile:
            return ToolResult(success=False, error="用户尚未创建画像，无法生成简历。请先在'个人画像'页填写信息。")

        # 获取 JD（可选）
        jd = jd_text
        if not jd and jd_url:
            service = ResumeService(self.llm)
            try:
                data = await service.extract_jd_from_url(jd_url)
                jd = data.get("raw_text") or _jd_to_text(data)
            except Exception as e:
                logger.warning(f"JD 抓取失败，按通用简历生成: {e}")

        service = ResumeService(self.llm)
        try:
            resume_md = await service.generate_resume(profile, jd)
            if not resume_md or len(resume_md) < 50:
                return ToolResult(success=False, error="简历生成失败，请检查画像信息是否完整")
            return ToolResult(success=True, data={
                "message": "简历已生成（Markdown 格式，可直接复制使用）",
                "resume_markdown": resume_md,
                "format": "markdown",
                "char_count": len(resume_md),
            })
        except Exception as e:
            logger.error(f"简历生成失败: {e}")
            return ToolResult(success=False, error=f"简历生成失败: {e}")


# ====================================================================
# 4. 求职信生成
# ====================================================================

class GenerateCoverLetterTool(BaseTool):
    """生成求职信/自荐信"""

    name = "generate_cover_letter"
    description = (
        "根据用户画像和目标岗位 JD 生成求职信/自荐信（Markdown，300-500 字，3 段式）。"
        "当用户说'帮我写求职信'、'写封自荐信'、'生成 cover letter'时调用。"
        "参数：jd_text 或 jd_url（目标 JD，必需），company（公司名，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "目标岗位 JD 文本（优先）"},
            "jd_url": {"type": "string", "description": "目标岗位 JD 链接（自动抓取）"},
            "company": {"type": "string", "description": "目标公司名（可选，用于称呼）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(
        self,
        jd_text: Optional[str] = None,
        jd_url: Optional[str] = None,
        company: Optional[str] = None,
    ) -> ToolResult:
        profile = _load_profile(self.db, self.user_id)
        if not profile:
            return ToolResult(success=False, error="用户尚未创建画像，无法生成求职信")

        jd = jd_text
        if not jd and jd_url:
            service = ResumeService(self.llm)
            try:
                data = await service.extract_jd_from_url(jd_url)
                jd = data.get("raw_text") or _jd_to_text(data)
            except Exception as e:
                return ToolResult(success=False, error=f"JD 抓取失败: {e}")
        if not jd:
            return ToolResult(success=False, error="请提供 jd_text 或 jd_url")

        service = ResumeService(self.llm)
        try:
            letter_md = await service.generate_cover_letter(profile, jd, company or "")
            if not letter_md or len(letter_md) < 50:
                return ToolResult(success=False, error="求职信生成失败")
            return ToolResult(success=True, data={
                "message": f"求职信已生成{('（致 ' + company + '）') if company else ''}",
                "cover_letter_markdown": letter_md,
                "format": "markdown",
            })
        except Exception as e:
            logger.error(f"求职信生成失败: {e}")
            return ToolResult(success=False, error=f"求职信生成失败: {e}")


# ====================================================================
# 5. 面试准备包
# ====================================================================

class PrepareInterviewTool(BaseTool):
    """生成面试准备包"""

    name = "prepare_interview"
    description = (
        "生成结构化面试准备包（Markdown），含：面试流程预判/公司调研方向/可能问题(按轮次)/"
        "STAR 例子映射/技术八股重点/反问问题/薄弱项提醒。"
        "当用户说'我要面试了帮我准备'、'准备一下XX公司的面试'、'面试辅导'时调用。"
        "参数：jd_text 或 jd_url（目标 JD，必需），company（公司名，可选），position（岗位名，可选）。"
        "也可基于已有投递记录准备面试：传入 company 会自动查找该公司的投递。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "目标岗位 JD 文本（优先）"},
            "jd_url": {"type": "string", "description": "目标岗位 JD 链接（自动抓取）"},
            "company": {"type": "string", "description": "目标公司名（可选，用于针对性准备）"},
            "position": {"type": "string", "description": "目标岗位名（可选）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    async def execute(
        self,
        jd_text: Optional[str] = None,
        jd_url: Optional[str] = None,
        company: Optional[str] = None,
        position: Optional[str] = None,
    ) -> ToolResult:
        profile = _load_profile(self.db, self.user_id)
        if not profile:
            return ToolResult(success=False, error="用户尚未创建画像，无法生成面试准备包")

        # 获取 JD
        jd = jd_text
        if not jd and jd_url:
            service = ResumeService(self.llm)
            try:
                data = await service.extract_jd_from_url(jd_url)
                jd = data.get("raw_text") or _jd_to_text(data)
            except Exception as e:
                return ToolResult(success=False, error=f"JD 抓取失败: {e}")

        # 若未提供 JD 但提供了 company，尝试从投递记录找 job_url
        if not jd and company:
            app = self.db.query(Application).filter(
                Application.user_id == self.user_id,
                Application.company.like(f"%{company}%"),
            ).order_by(Application.updated_at.desc().nullslast()).first()
            if app and app.job_url:
                service = ResumeService(self.llm)
                try:
                    data = await service.extract_jd_from_url(app.job_url)
                    jd = data.get("raw_text") or _jd_to_text(data)
                    if not position:
                        position = app.position
                except Exception as e:
                    logger.warning(f"从投递记录抓取 JD 失败: {e}")

        if not jd:
            return ToolResult(success=False, error="请提供 jd_text 或 jd_url，或确保有该公司的投递记录含 job_url")

        service = ResumeService(self.llm)
        try:
            prep_md = await service.prepare_interview(profile, jd, company or "", position or "")
            if not prep_md or len(prep_md) < 50:
                return ToolResult(success=False, error="面试准备包生成失败")
            return ToolResult(success=True, data={
                "message": f"面试准备包已生成{('（' + company + '）') if company else ''}",
                "interview_prep_markdown": prep_md,
                "format": "markdown",
            })
        except Exception as e:
            logger.error(f"面试准备包生成失败: {e}")
            return ToolResult(success=False, error=f"面试准备包生成失败: {e}")


# ====================================================================
# 6. 投递策略建议
# ====================================================================

class GetApplicationAdviceTool(BaseTool):
    """基于历史投递数据生成策略建议"""

    name = "get_application_advice"
    description = (
        "基于用户的历史投递统计数据，生成求职策略建议（Markdown），含：现状诊断/问题分析/"
        "优化建议/投递节奏建议。当用户说'我的投递策略有问题吗'、'帮我复盘求职'、"
        "'为什么回复率低'、'接下来该怎么投'时调用。"
        "无需参数，自动聚合用户的投递统计。建议投递记录达到 5 条以上再使用，数据太少意义不大。"
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
        from collections import Counter
        from datetime import datetime, timezone, timedelta

        apps = self.db.query(Application).filter(
            Application.user_id == self.user_id,
            Application.status != "withdrawn",
        ).all()

        if not apps:
            return ToolResult(success=True, data={
                "message": "你还没有投递记录，无法生成策略建议。建议先投递 5-10 家公司再复盘。",
                "advice_markdown": "暂无投递数据，无法分析。",
            })

        total = len(apps)
        status_counter = Counter(a.status for a in apps)
        replied = sum(status_counter.get(s, 0) for s in ["assessment", "interview", "offer", "rejected"])
        offer_count = status_counter.get("offer", 0)
        rejected_count = status_counter.get("rejected", 0)

        # 拒绝环节分布
        rejection_stages = Counter(
            a.rejection_stage for a in apps
            if a.status == "rejected" and a.rejection_stage
        )

        # 来源分布
        source_counter = Counter(a.source or "未知" for a in apps)

        # 近 30 天投递趋势
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        recent = [a for a in apps if a.applied_at and _to_aware(a.applied_at) >= thirty_days_ago]

        # 公司维度
        companies = Counter(a.company for a in apps)

        # 优先级分布
        priority_counter = Counter(a.priority or "medium" for a in apps)

        stats = {
            "total": total,
            "by_status": dict(status_counter),
            "reply_rate": f"{(replied / total * 100):.1f}%" if total else "0%",
            "offer_rate": f"{(offer_count / total * 100):.1f}%" if total else "0%",
            "replied": replied,
            "offer_count": offer_count,
            "rejected_count": rejected_count,
            "rejection_stages": dict(rejection_stages),
            "by_source": dict(source_counter),
            "recent_30d_count": len(recent),
            "company_count": len(companies),
            "by_priority": dict(priority_counter),
        }

        # 数据太少时给提示
        if total < 5:
            return ToolResult(success=True, data={
                "message": f"当前只有 {total} 条投递记录，数据量偏少，分析结果仅供参考。",
                "advice_markdown": f"目前投递记录仅 {total} 条，建议累计 5-10 条后再做策略复盘。\n\n当前回复率 {stats['reply_rate']}，继续投递积累数据。",
                "stats": stats,
            })

        service = ResumeService(self.llm)
        try:
            advice_md = await service.get_application_advice(stats)
            if not advice_md:
                return ToolResult(success=False, error="策略建议生成失败")
            return ToolResult(success=True, data={
                "message": "投递策略建议已生成（基于你的历史数据）",
                "advice_markdown": advice_md,
                "format": "markdown",
                "stats": stats,
            })
        except Exception as e:
            logger.error(f"投递建议生成失败: {e}")
            return ToolResult(success=False, error=f"投递建议生成失败: {e}", data={"stats": stats})


# ====================================================================
# 辅助函数
# ====================================================================

def _jd_to_text(data: dict) -> str:
    """把结构化 JD dict 转为文本"""
    if not data:
        return ""
    parts = []
    if data.get("title"):
        parts.append(f"岗位：{data['title']}")
    if data.get("company"):
        parts.append(f"公司：{data['company']}")
    if data.get("location"):
        parts.append(f"地点：{data['location']}")
    if data.get("salary"):
        parts.append(f"薪资：{data['salary']}")
    if data.get("responsibilities"):
        parts.append("岗位职责：\n" + "\n".join(f"- {r}" for r in data["responsibilities"]))
    if data.get("requirements"):
        parts.append("任职要求：\n" + "\n".join(f"- {r}" for r in data["requirements"]))
    if data.get("skills"):
        parts.append("技能要求：" + "、".join(data["skills"]))
    return "\n\n".join(parts)


def _to_aware(dt) -> "datetime":
    """确保 datetime 带时区"""
    from datetime import timezone
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
