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
    description = "获取当前用户的个人画像，包含基本信息、教育经历、工作经历、技能、项目经历、语言能力、证书、获奖、论文、专利、开放题答案库、求职意向。当用户询问自己的信息、或填写表单需要用户数据时调用。"
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
            "projects": profile.projects or [],
            "skills": profile.skills or [],
            "summary": profile.summary or {},
            "certifications": profile.certifications or [],
            "languages": profile.languages or [],
            "awards": profile.awards or [],
            "essays": profile.essays or [],
            "publications": profile.publications or [],
            "patents": profile.patents or [],
            "job_intent": profile.job_intent or {},
        })


class UpdateProfileTool(BaseTool):
    """更新用户画像"""

    name = "update_profile"
    description = "更新用户画像的某个部分。可更新的字段：basic_info(基本信息)、education(教育经历数组)、experience(工作经历数组)、projects(项目经历数组)、skills(技能数组)、summary(自我评价)、certifications(证书数组)、languages(语言能力数组)、awards(获奖数组)、essays(开放题答案数组)、publications(论文数组)、patents(专利数组)、job_intent(求职意向)。传入的字段会整体覆盖原值。注意：身份证号、家庭住址、银行卡、护照、紧急联系人等敏感字段会被自动剔除、不会保存。"
    parameters = {
        "type": "object",
        "properties": {
            "basic_info": {
                "type": "object",
                "description": "基本信息对象，包含 name/english_name/phone/email/gender/birth/location/ethnicity/political_status/marital_status/native_place/household_type/wechat/qq/website/github/linkedin/english_level/driving_license/job_status/current_company/current_title/years_of_experience/highest_education/available_date 等非敏感字段",
            },
            "education": {
                "type": "array",
                "description": "教育经历数组，每项含 school/major/degree/school_type/edu_form/study_mode/minor/faculty/start_date/end_date/gpa/ranking/courses/description",
                "items": {"type": "object"},
            },
            "experience": {
                "type": "array",
                "description": "工作经历数组，每项含 company/position/department/industry/city/employment_type/location_mode/team_size/start_date/end_date/description/achievements/technologies",
                "items": {"type": "object"},
            },
            "projects": {
                "type": "array",
                "description": "项目经历数组，每项含 name/role/organization/start_date/end_date/url/demo_url/description/highlights/tech_stack",
                "items": {"type": "object"},
            },
            "skills": {
                "type": "array",
                "description": "技能列表，如 ['Python', 'Java']",
                "items": {"type": "string"},
            },
            "summary": {
                "type": "object",
                "description": "自我评价，含 self_intro/strengths/career_goal/expected_salary/expected_location/expected_position",
            },
            "certifications": {
                "type": "array",
                "description": "证书数组，每项含 name/issuer/date/score",
                "items": {"type": "object"},
            },
            "languages": {
                "type": "array",
                "description": "语言能力数组，每项含 name/proficiency/test_score，如 [{'name': '英语', 'proficiency': '流利', 'test_score': 'CET-6'}]",
                "items": {"type": "object"},
            },
            "awards": {
                "type": "array",
                "description": "获奖数组，每项含 name/level/issuer/date/description",
                "items": {"type": "object"},
            },
            "essays": {
                "type": "array",
                "description": "开放题答案数组，每项含 question/answer/tag（tag 为版本标签，如 互联网版/国央企版）",
                "items": {"type": "object"},
            },
            "publications": {
                "type": "array",
                "description": "论文/发表物数组，每项含 title/venue/level/authors/role/date/doi/description（level 如 SCI/EI/中文核心，role 如 第一作者/共同一作）",
                "items": {"type": "object"},
            },
            "patents": {
                "type": "array",
                "description": "专利数组，每项含 name/patent_no/type/status/holder/inventors/date/description（type 如 发明专利，status 如 已授权/实审中/已申请）",
                "items": {"type": "object"},
            },
            "job_intent": {
                "type": "object",
                "description": "求职意向，含 role/cities/salary_min/salary_max/job_type/target_positions/target_cities/expected_salary/work_type/availability/target_industry/target_level/remote_preference/willing_to_relocate/willing_to_travel/current_salary",
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
        projects: Optional[list] = None,
        skills: Optional[list] = None,
        summary: Optional[dict] = None,
        certifications: Optional[list] = None,
        languages: Optional[list] = None,
        awards: Optional[list] = None,
        essays: Optional[list] = None,
        publications: Optional[list] = None,
        patents: Optional[list] = None,
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
        if projects is not None:
            profile.projects = projects
            updated_fields.append("projects")
        if skills is not None:
            profile.skills = skills
            updated_fields.append("skills")
        if summary is not None:
            profile.summary = summary
            updated_fields.append("summary")
        if certifications is not None:
            profile.certifications = certifications
            updated_fields.append("certifications")
        if languages is not None:
            profile.languages = languages
            updated_fields.append("languages")
        if awards is not None:
            profile.awards = awards
            updated_fields.append("awards")
        if essays is not None:
            profile.essays = essays
            updated_fields.append("essays")
        if publications is not None:
            profile.publications = publications
            updated_fields.append("publications")
        if patents is not None:
            profile.patents = patents
            updated_fields.append("patents")
        if job_intent is not None:
            profile.job_intent = job_intent
            updated_fields.append("job_intent")

        self.db.commit()

        # 画像演化：异步（后台）提炼长期记忆，不阻塞 Agent 主流程
        if any(f in ("experience", "skills", "education", "projects", "job_intent")
               for f in updated_fields):
            try:
                import asyncio
                from app.agent.memory.evolution import trigger_evolution
                asyncio.get_running_loop().create_task(trigger_evolution(self.user_id, "agent"))
            except Exception:
                pass

        return ToolResult(success=True, data={
            "message": f"画像已更新，更新字段: {', '.join(updated_fields) if updated_fields else '无'}",
            "updated_fields": updated_fields,
        })
