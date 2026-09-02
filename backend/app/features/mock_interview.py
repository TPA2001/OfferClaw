"""
模拟面试 Feature

根据简历 + JD 生成定制面试题目，支持结构化反馈。
借鉴 CareerDesk 的 grill 模块，但结合 OfferCabin 的岗位真实性判断能力，
可以针对性地追问风险点。

能力：
- 生成面试题集（技术面/行为面/反问环节）
- 模拟面试对话（多轮）
- 答案评估与反馈
- 针对性追问（基于岗位风险点）
"""

import json
import logging
import re
from typing import Optional

from app.core.llm import LLMProvider, LLMResponse, Message

logger = logging.getLogger("offercabin.features.mock_interview")


class MockInterviewService:
    """模拟面试服务"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def _chat(self, system: str, user: str, temperature: float = 0.6) -> str:
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]
        resp: LLMResponse = await self.llm.chat(messages, temperature=temperature)
        return resp.content or ""

    async def generate_questions(
        self,
        jd_text: str,
        profile_text: Optional[str] = None,
        interview_type: str = "technical",
        count: int = 10,
    ) -> dict:
        """
        生成定制面试题集。

        Args:
            jd_text: JD 文本
            profile_text: 简历文本（可选，用于个性化出题）
            interview_type: 面试类型 technical/behavioral/system_design
            count: 题目数量

        Returns:
            {
                "questions": [{"q": "题目", "type": "类型", "difficulty": "easy/medium/hard",
                               "key_points": ["得分点"], "reference_answer": "参考答案"}],
                "advice": "面试建议"
            }
        """
        type_label = {
            "technical": "技术面",
            "behavioral": "行为面（BQ）",
            "system_design": "系统设计",
            "hr": "HR 面",
        }.get(interview_type, "技术面")

        system = (
            f"你是资深{type_label}面试官。根据 JD 和候选人简历生成定制面试题集。\n"
            "要求：\n"
            "1. 题目紧扣 JD 要求，不泛泛而问\n"
            "2. 如有简历，针对简历中的项目经历追问\n"
            "3. 每题给出关键得分点和参考答案\n"
            "4. 难度分布：30% easy / 50% medium / 20% hard\n\n"
            "输出 JSON：\n"
            "{\n"
            '  "questions": [\n'
            '    {"q": "题目", "type": "technical|behavioral|system_design", '
            '"difficulty": "easy|medium|hard", "key_points": ["得分点1"], '
            '"reference_answer": "参考答案要点"}\n'
            "  ],\n"
            '  "advice": "整体面试建议"\n'
            "}\n"
            "只输出 JSON。"
        )

        user_parts = [f"JD 内容：\n{jd_text}"]
        if profile_text:
            user_parts.append(f"候选人简历：\n{profile_text}")
        user_parts.append(f"面试类型：{type_label}")
        user_parts.append(f"题目数量：{count}")

        user = "\n\n".join(user_parts)

        try:
            raw = await self._chat(system, user, temperature=0.4)
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"生成面试题失败: {e}")

        return {
            "questions": [],
            "advice": "面试题生成服务暂时不可用",
        }

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        key_points: Optional[list[str]] = None,
    ) -> dict:
        """
        评估面试答案。

        Returns:
            {
                "score": 0-100,
                "covered_points": ["已覆盖的得分点"],
                "missed_points": ["遗漏的得分点"],
                "improvement": "改进建议",
                "model_answer": "参考答案"
            }
        """
        system = (
            "你是面试评估专家。评估候选人的答案。\n"
            "输出 JSON：\n"
            "{\n"
            '  "score": 0-100,\n'
            '  "covered_points": ["已覆盖的得分点"],\n'
            '  "missed_points": ["遗漏的得分点"],\n'
            '  "improvement": "改进建议",\n'
            '  "model_answer": "参考答案"\n'
            "}\n只输出 JSON。"
        )
        user = f"题目：{question}\n\n候选人答案：{answer}"
        if key_points:
            user += f"\n\n关键得分点：{key_points}"

        try:
            raw = await self._chat(system, user, temperature=0.3)
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"评估答案失败: {e}")

        return {"score": 0, "improvement": "评估服务暂时不可用"}


# ===== 公共边界 =====
_service: Optional[MockInterviewService] = None


def get_mock_interview_service(llm: Optional[LLMProvider] = None) -> MockInterviewService:
    """获取模拟面试服务单例"""
    global _service
    if _service is None or llm is not None:
        from app.core.llm import get_gen_provider
        _llm = llm or get_gen_provider()
        _service = MockInterviewService(_llm)
    return _service
