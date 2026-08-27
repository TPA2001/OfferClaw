"""
岗位分析工具

补齐 agent 在岗位筛选环节的核心能力：
- verify_job_authenticity：岗位真实性判断（识别中介/培训贷/虚假招聘）
- evaluate_job：岗位综合评估（一次性完成真实性 + 匹配度 + 投递建议）

设计原则：
- 真实性判断和匹配度评分可独立调用，也可通过 evaluate_job 一次性串联
- 所有工具返回结构化 data，agent 可直接用于生成回复
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.llm import LLMProvider
from app.services.resume_service import ResumeService
from ..runtime.base_tool import BaseTool, ToolResult

logger = logging.getLogger("offerclaw.agent.tools.job_eval")


def _jd_to_text(data: dict) -> str:
    """把结构化 JD dict 转为文本（与 job_tools 保持一致）"""
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


def _load_profile(db: Session, user_id: str) -> Optional[dict]:
    """加载用户画像并转为 dict"""
    from app.models.profile import Profile
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


async def _resolve_jd(
    llm: LLMProvider,
    jd_text: Optional[str],
    jd_url: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    解析 JD 内容：优先用 jd_text，否则从 jd_url 抓取。

    Returns:
        (jd_content, error_message)
    """
    if jd_text:
        return jd_text, None
    if jd_url:
        service = ResumeService(llm)
        try:
            data = await service.extract_jd_from_url(jd_url)
            jd = data.get("raw_text") or _jd_to_text(data)
            if not jd:
                return None, "从 URL 抓取 JD 失败：页面内容为空"
            return jd, None
        except Exception as e:
            return None, f"JD 抓取失败: {e}"
    return None, "请提供 jd_text 或 jd_url"


# ====================================================================
# 1. 岗位真实性判断
# ====================================================================

class VerifyJobAuthenticityTool(BaseTool):
    """判断岗位真实性与风险，识别虚假/中介/培训贷等骗局"""

    name = "verify_job_authenticity"
    description = (
        "判断岗位真实性与风险等级，识别中介/培训贷/虚假薪资/皮包公司/收费骗局/信息矛盾等风险信号。"
        "返回风险等级(safe/low/medium/high/danger)、风险评分、风险信号清单和建议。"
        "当用户说'这个岗位靠谱吗'、'是不是中介'、'帮我看看这家公司真假'、'这个招聘可信吗'时调用。"
        "这是投递前的安全检查，建议在评估任何岗位时优先调用。"
        "参数：jd_text（JD文本，优先）或 jd_url（JD链接，自动抓取），company（公司名，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "岗位 JD 文本（优先使用）"},
            "jd_url": {"type": "string", "description": "岗位 JD 链接（当无 jd_text 时自动抓取）"},
            "company": {"type": "string", "description": "公司名（可选，辅助判断皮包公司）"},
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
        jd, err = await _resolve_jd(self.llm, jd_text, jd_url)
        if err:
            return ToolResult(success=False, error=err)

        service = ResumeService(self.llm)
        try:
            result = await service.verify_authenticity(jd, company or "")
            risk_level = result.get("risk_level", "unknown")
            risk_score = result.get("risk_score", 50)
            auth_score = result.get("authenticity_score", 50)
            signals = result.get("signals", [])

            # 生成结论
            level_emoji = {
                "safe": "🟢", "low": "🟢", "medium": "🟡",
                "high": "🔴", "danger": "🚨", "unknown": "⚪",
            }
            emoji = level_emoji.get(risk_level, "⚪")
            signal_count = len(signals)
            summary = result.get("summary", "")

            message = f"{emoji} 真实性评估：{risk_level}（可信度 {auth_score}/100，风险 {risk_score}/100）"
            if signal_count:
                message += f"\n检测到 {signal_count} 个风险信号"
            if summary:
                message += f"\n{summary}"

            return ToolResult(success=True, data={
                "message": message,
                **result,
            })
        except Exception as e:
            logger.error(f"真实性判断失败: {e}")
            return ToolResult(success=False, error=f"真实性判断失败: {e}")


# 3. 岗位综合评估（真实性 + 匹配度 + 投递建议）
# ====================================================================

class EvaluateJobTool(BaseTool):
    """岗位综合评估：一次性完成真实性判断 + 匹配度评分 + 投递建议"""

    name = "evaluate_job"
    description = (
        "岗位综合评估：一次性完成真实性判断 + 匹配度评分 + 投递建议。"
        "这是最推荐的岗位分析入口，会自动串联真实性检查和匹配度评分，给出最终投递决策。"
        "当用户说'帮我评估这个岗位'、'这个机会值不值得投'、'综合分析一下'、'这个岗位怎么样'时调用。"
        "参数：jd_text（JD文本，优先）或 jd_url（JD链接，自动抓取），company（公司名，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "jd_text": {"type": "string", "description": "岗位 JD 文本（优先使用）"},
            "jd_url": {"type": "string", "description": "岗位 JD 链接（当无 jd_text 时自动抓取）"},
            "company": {"type": "string", "description": "公司名（可选）"},
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str, llm: LLMProvider):
        self.db = db
        self.user_id = user_id
        self.llm = llm

    @staticmethod
    async def _noop():
        """空操作协程，用于画像缺失时占位"""
        return None

    async def execute(
        self,
        jd_text: Optional[str] = None,
        jd_url: Optional[str] = None,
        company: Optional[str] = None,
    ) -> ToolResult:
        # 1. 解析 JD
        jd, err = await _resolve_jd(self.llm, jd_text, jd_url)
        if err:
            return ToolResult(success=False, error=err)

        # 2. 加载画像（匹配度评分需要）
        profile = _load_profile(self.db, self.user_id)

        service = ResumeService(self.llm)

        # 3. 并行执行真实性判断 + 匹配度评分
        # 真实性判断不依赖画像，匹配度评分依赖画像
        tasks = [service.verify_authenticity(jd, company or "")]
        task_names = ["authenticity"]

        if profile:
            tasks.append(service.score_job_match(profile, jd))
            task_names.append("match")
        else:
            tasks.append(self._noop())
            task_names.append("match_skipped")

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"综合评估并行执行失败: {e}")
            return ToolResult(success=False, error=f"综合评估失败: {e}")

        verify_result = results[0]
        if isinstance(verify_result, Exception):
            logger.error(f"真实性判断异常: {verify_result}")
            verify_result = {
                "risk_level": "unknown", "risk_score": 50,
                "authenticity_score": 50, "signals": [],
                "summary": "真实性判断失败", "advice": "",
            }

        match_result = results[1] if len(results) > 1 else None
        if isinstance(match_result, Exception):
            logger.error(f"匹配度评分异常: {match_result}")
            match_result = None

        # 4. 综合决策
        risk_level = verify_result.get("risk_level", "unknown")
        auth_score = verify_result.get("authenticity_score", 50)

        if match_result:
            match_score = match_result.get("score", 0)
            match_level = match_result.get("level", "未知")
            match_veto = match_result.get("veto", False)
        else:
            match_score = None
            match_level = None
            match_veto = False

        # 决策逻辑
        if risk_level in ("high", "danger"):
            verdict = "🚫 不建议投递（真实性存疑）"
            verdict_reason = f"风险等级 {risk_level}，存在严重可信度问题"
        elif match_veto:
            verdict = "🚫 不建议投递（硬性条件不符）"
            verdict_reason = match_result.get("suggestion", "硬性条件不满足岗位要求")
        elif risk_level == "medium":
            verdict = "⚠️ 谨慎投递（需核实真实性）"
            verdict_reason = "存在可疑信号，建议先核实公司信息再投递"
        elif match_score is not None and match_score >= 70 and auth_score >= 70:
            verdict = "✅ 建议投递"
            verdict_reason = f"真实性良好且匹配度高（{match_score}分）"
        elif match_score is not None and match_score >= 55:
            verdict = "⚠️ 谨慎投递"
            verdict_reason = f"匹配度一般（{match_score}分），可尝试但有差距"
        elif match_score is not None:
            verdict = "🚫 不建议投递（匹配度过低）"
            verdict_reason = f"匹配度仅 {match_score} 分，差距较大"
        else:
            verdict = "⚠️ 无法完整评估"
            verdict_reason = "缺少画像信息，无法评估匹配度，请先完善个人画像"

        # 5. 构造回复
        auth_emoji = {"safe": "🟢", "low": "🟢", "medium": "🟡",
                      "high": "🔴", "danger": "🚨"}.get(risk_level, "⚪")

        message_lines = [
            f"## 岗位综合评估报告\n",
            f"- 真实性：{auth_emoji} {risk_level}（可信度 {auth_score}/100）",
        ]
        if match_score is not None:
            match_emoji = "🟢" if match_score >= 70 else ("🟡" if match_score >= 55 else "🔴")
            message_lines.append(f"- 匹配度：{match_emoji} {match_level}（{match_score}/100）")
        else:
            message_lines.append("- 匹配度：⚪ 未评估（缺少画像）")
        message_lines.append(f"- 结论：{verdict}")

        if verify_result.get("signals"):
            message_lines.append(f"\n### 风险信号")
            for sig in verify_result["signals"]:
                sev = sig.get("severity", "low")
                sev_emoji = {"high": "🔴", "mid": "🟡", "low": "🟢"}.get(sev, "⚪")
                message_lines.append(f"- {sev_emoji} **{sig.get('type', '?')}**：{sig.get('detail', '')}")

        if match_result and match_result.get("strengths"):
            message_lines.append(f"\n### 匹配优势")
            for s in match_result["strengths"]:
                message_lines.append(f"- {s}")

        if match_result and match_result.get("gaps"):
            message_lines.append(f"\n### 差距与不足")
            for g in match_result["gaps"]:
                message_lines.append(f"- {g}")

        if verify_result.get("advice"):
            message_lines.append(f"\n### 真实性建议\n{verify_result['advice']}")

        if match_result and match_result.get("suggestion"):
            message_lines.append(f"\n### 投递建议\n{match_result['suggestion']}")

        message = "\n".join(message_lines)

        data = {
            "message": message,
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "authenticity": verify_result,
            "match": match_result,
        }
        if company:
            data["company"] = company

        return ToolResult(success=True, data=data)
