"""
智能填写相关工具
封装现有 SmartFillService 和 FieldMatcher 为 agent 工具
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.profile import Profile
from app.services.smart_fill import SmartFillService
from app.automation import FieldMatcher
from ..runtime.base_tool import BaseTool, ToolResult

logger = logging.getLogger("offerclaw.agent.tools.smart_fill")


class ExtractFormFieldsTool(BaseTool):
    """从 URL 提取表单字段"""

    name = "extract_form_fields"
    description = "从指定 URL 抓取网页并自动识别表单字段（input/select/textarea）。返回字段列表及页面信息。当用户说'帮我填这个表单 https://...'、'识别这个页面的字段'时调用。注意：会启动无头浏览器抓取页面，耗时可能 10-30 秒。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标网页 URL"},
        },
        "required": ["url"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, url: str) -> ToolResult:
        service = SmartFillService()
        try:
            result = await service.extract_fields_from_url(url)
            # 截图字段过大，去掉
            result.pop("screenshot", None)
            return ToolResult(success=True, data={
                "message": f"从 {url} 提取到 {result.get('field_count', 0)} 个字段",
                **result,
            })
        except Exception as e:
            logger.error(f"字段提取失败: {e}")
            return ToolResult(success=False, error=f"页面抓取失败: {str(e)}")


class MatchFieldsTool(BaseTool):
    """将表单字段与用户画像进行 LLM 语义匹配"""

    name = "match_fields_to_profile"
    description = "将提取的表单字段与用户画像进行 LLM 语义匹配，返回每个字段的建议填写值、置信度和数据来源。低置信度字段需要用户人工确认。敏感字段（身份证、住址）由本地浏览器扩展填写，本工具不接触原文。"
    parameters = {
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "description": "表单字段列表，每项含 id/label/type/selector 等字段（来自 extract_form_fields 工具）",
                "items": {"type": "object"},
            },
        },
        "required": ["fields"],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, fields: list) -> ToolResult:
        # 加载用户画像
        profile = self.db.query(Profile).filter(Profile.user_id == self.user_id).first()
        if not profile:
            return ToolResult(success=False, error="用户尚未创建画像，无法匹配")
        profile_data = {
            "basic_info": profile.basic_info or {},
            "education": profile.education or [],
            "experience": profile.experience or [],
            "skills": profile.skills or [],
            "job_intent": profile.job_intent or {},
        }

        matcher = FieldMatcher()
        try:
            result = await matcher.match(
                fields=fields,
                user_id=self.user_id,
                profile=profile_data,
                db=None,  # MVP 不做订阅校验
            )
            mappings = result.get("mappings", [])

            # 统计置信度
            high_conf = sum(1 for m in mappings if (m.get("confidence") or 0) >= 0.7)
            low_conf = sum(1 for m in mappings if (m.get("confidence") or 0) < 0.4)

            return ToolResult(success=True, data={
                "mappings": mappings,
                "profile_used": result.get("profile_used", True),
                "stats": {
                    "total": len(mappings),
                    "high_confidence": high_conf,
                    "low_confidence": low_conf,
                },
                "message": f"匹配完成：共 {len(mappings)} 字段，高置信度 {high_conf} 个，低置信度 {low_conf} 个需人工确认",
            })
        except Exception as e:
            logger.error(f"字段匹配失败: {e}")
            return ToolResult(success=False, error=f"匹配失败: {str(e)}")
