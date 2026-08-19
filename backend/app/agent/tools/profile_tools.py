"""
用户画像相关工具
"""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.profile import Profile
from ..runtime.base_tool import BaseTool, ToolResult


class GetProfileTool(BaseTool):
    """获取当前用户的画像"""

    name = "get_profile"
    description = "获取当前用户的个人画像，包含基本信息、教育经历、工作经历、技能、求职意向。当用户询问自己的信息、或填写表单需要用户数据时调用。"
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self) -> ToolResult:
        profile = self.db.query(Profile).filter(Profile.user_id == self.user_id).first()
        if not profile:
            return ToolResult(success=True, data={"message": "用户尚未创建画像", "profile": None})
        return ToolResult(success=True, data={
            "basic_info": profile.basic_info or {},
            "education": profile.education or [],
            "experience": profile.experience or [],
            "skills": profile.skills or [],
            "job_intent": profile.job_intent or {},
        })


class UpdateProfileTool(BaseTool):
    """更新用户画像"""

    name = "update_profile"
    description = "更新用户画像的某个部分。可更新的字段：basic_info(基本信息)、education(教育经历数组)、experience(工作经历数组)、skills(技能数组)、job_intent(求职意向)。传入的字段会整体覆盖原值。注意：身份证号、家庭住址、银行卡、护照、紧急联系人等敏感字段会被自动剔除、不会保存。"
    parameters = {
        "type": "object",
        "properties": {
            "basic_info": {
                "type": "object",
                "description": "基本信息对象，包含 name/phone/email/gender/birth/ethnicity/political_status/marital_status/native_place/wechat/qq/website/github/linkedin/english_level/driving_license/job_status 等非敏感字段",
            },
            "education": {
                "type": "array",
                "description": "教育经历数组，每项含 school/major/degree/start_date/end_date",
                "items": {"type": "object"},
            },
            "experience": {
                "type": "array",
                "description": "工作经历数组，每项含 company/title/start_date/end_date/description",
                "items": {"type": "object"},
            },
            "skills": {
                "type": "array",
                "description": "技能列表，如 ['Python', 'Java']",
                "items": {"type": "string"},
            },
            "job_intent": {
                "type": "object",
                "description": "求职意向，含 role/cities/salary_min/salary_max/job_type",
            },
        },
        "required": [],
    }

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(
        self,
        basic_info: Optional[dict] = None,
        education: Optional[list] = None,
        experience: Optional[list] = None,
        skills: Optional[list] = None,
        job_intent: Optional[dict] = None,
    ) -> ToolResult:
        profile = self.db.query(Profile).filter(Profile.user_id == self.user_id).first()
        if not profile:
            profile = Profile(user_id=self.user_id)
            self.db.add(profile)

        updated_fields = []
        if basic_info is not None:
            # 安全：剔除敏感字段（身份证/住址/银行卡/护照/紧急联系人等），后端绝不持久化 PII
            from app.core.sanitizer import strip_sensitive_basic
            profile.basic_info = strip_sensitive_basic(basic_info)
            updated_fields.append("basic_info")
        if education is not None:
            profile.education = education
            updated_fields.append("education")
        if experience is not None:
            profile.experience = experience
            updated_fields.append("experience")
        if skills is not None:
            profile.skills = skills
            updated_fields.append("skills")
        if job_intent is not None:
            profile.job_intent = job_intent
            updated_fields.append("job_intent")

        self.db.commit()
        return ToolResult(success=True, data={
            "message": f"画像已更新，更新字段: {', '.join(updated_fields) if updated_fields else '无'}",
            "updated_fields": updated_fields,
        })
