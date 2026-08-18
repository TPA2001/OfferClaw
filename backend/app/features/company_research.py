"""
公司调研 Feature

基于公开信息整理公司/岗位调研报告。
借鉴 CareerDesk 的 research 模块，但结合 OfferClaw 的 Boss 搜索能力，
可以直接从 Boss 搜索结果中提取公司信息。

能力：
- 公司基本信息（行业/规模/融资/地点）
- 在招岗位列表（复用 Boss 搜索）
- 面试评价摘要（基于 LLM 分析）
- 调研报告生成（LLM 结构化输出）
"""

import logging
from typing import Optional

from app.core.llm import LLMProvider, LLMResponse, Message

logger = logging.getLogger("offerclaw.features.company_research")


class CompanyResearchService:
    """公司调研服务"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def _chat(self, system: str, user: str, temperature: float = 0.5) -> str:
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]
        resp: LLMResponse = await self.llm.chat(messages, temperature=temperature)
        return resp.content or ""

    async def research_company(
        self,
        company_name: str,
        job_position: Optional[str] = None,
        known_info: Optional[str] = None,
    ) -> dict:
        """
        调研一家公司，生成结构化报告。

        Args:
            company_name: 公司名称
            job_position: 目标岗位（可选，用于针对性分析）
            known_info: 已知信息（可选，如 Boss 搜索结果中的公司简介）

        Returns:
            {
                "company": "公司名",
                "industry": "行业",
                "summary": "公司概况",
                "pros": ["优势1", ...],
                "cons": ["风险1", ...],
                "interview_tips": ["面试建议1", ...],
                "salary_reference": "薪资参考",
                "report": "完整调研报告（Markdown）"
            }
        """
        system = (
            "你是求职调研分析师。基于已知信息生成公司调研报告。\n"
            "要求客观、有据、不编造。信息不足时明确标注'需要进一步确认'。\n"
            "输出 JSON，字段如下：\n"
            "{\n"
            '  "industry": "所属行业",\n'
            '  "summary": "公司概况（2-3句话）",\n'
            '  "pros": ["优势1", "优势2"],\n'
            '  "cons": ["风险1", "风险2"],\n'
            '  "interview_tips": ["面试建议1"],\n'
            '  "salary_reference": "该岗位薪资参考范围",\n'
            '  "report": "完整调研报告（Markdown格式，含来源标注）"\n'
            "}\n"
            "只输出 JSON，不要其他文本。"
        )

        user_parts = [f"公司名称：{company_name}"]
        if job_position:
            user_parts.append(f"目标岗位：{job_position}")
        if known_info:
            user_parts.append(f"已知信息：\n{known_info}")
        else:
            user_parts.append("已知信息：无（请基于公开知识分析，标注不确定性）")

        user = "\n".join(user_parts)

        try:
            raw = await self._chat(system, user, temperature=0.3)
            import json
            import re
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                data = json.loads(json_match.group())
                data["company"] = company_name
                return data
        except Exception as e:
            logger.error(f"公司调研失败: {e}")

        return {
            "company": company_name,
            "industry": "未知",
            "summary": "调研服务暂时不可用",
            "pros": [],
            "cons": [],
            "interview_tips": [],
            "salary_reference": "未知",
            "report": f"# {company_name} 调研报告\n\n调研服务暂时不可用，请稍后重试。",
        }


# ===== 公共边界 =====
_service: Optional[CompanyResearchService] = None


def get_company_research_service(llm: Optional[LLMProvider] = None) -> CompanyResearchService:
    """获取公司调研服务单例"""
    global _service
    if _service is None or llm is not None:
        from app.core.llm import get_gen_provider
        _llm = llm or get_gen_provider()
        _service = CompanyResearchService(_llm)
    return _service
