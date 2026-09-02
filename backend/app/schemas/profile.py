"""
用户画像 Schema

定义用户画像相关的请求/响应 Pydantic 模型。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class BasicInfo(BaseModel):
    """基本信息（均为非敏感字段；身份证/住址/银行卡/护照等敏感字段不在此结构，一律不存储）"""
    name: Optional[str] = None
    english_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth: Optional[str] = None
    age: Optional[str] = None
    location: Optional[str] = None
    ethnicity: Optional[str] = None
    political_status: Optional[str] = None
    marital_status: Optional[str] = None
    native_place: Optional[str] = None
    household_type: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    health: Optional[str] = None
    wechat: Optional[str] = None
    qq: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    english_level: Optional[str] = None
    driving_license: Optional[str] = None
    job_status: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    years_of_experience: Optional[str] = None
    highest_education: Optional[str] = None
    available_date: Optional[str] = None


class EducationItem(BaseModel):
    """教育经历"""
    school: Optional[str] = None
    major: Optional[str] = None
    degree: Optional[str] = None
    school_type: Optional[str] = None
    edu_form: Optional[str] = None
    study_mode: Optional[str] = None
    minor: Optional[str] = None
    faculty: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    graduation_status: Optional[str] = None
    gpa: Optional[str] = None
    ranking: Optional[str] = None
    courses: Optional[str] = None
    description: Optional[str] = None


class ExperienceItem(BaseModel):
    """工作经历"""
    company: Optional[str] = None
    title: Optional[str] = None
    department: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    employment_type: Optional[str] = None
    location_mode: Optional[str] = None
    team_size: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    description: Optional[str] = None
    achievements: Optional[list[str]] = None
    technologies: Optional[str] = None


class ProjectItem(BaseModel):
    """项目经历"""
    name: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    url: Optional[str] = None
    demo_url: Optional[str] = None
    description: Optional[str] = None
    highlights: Optional[str] = None
    tech_stack: Optional[list[str]] = None


class LanguageItem(BaseModel):
    """语言能力"""
    name: Optional[str] = None
    proficiency: Optional[str] = None
    test_score: Optional[str] = None


class AwardItem(BaseModel):
    """获奖/荣誉"""
    name: Optional[str] = None
    level: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class EssayItem(BaseModel):
    """开放题答案（网申通用问题，可存多版本）"""
    question: Optional[str] = None
    answer: Optional[str] = None
    tag: Optional[str] = None


class PublicationItem(BaseModel):
    """论文/发表物"""
    title: Optional[str] = None
    venue: Optional[str] = None
    level: Optional[str] = None
    authors: Optional[str] = None
    role: Optional[str] = None
    date: Optional[str] = None
    doi: Optional[str] = None
    description: Optional[str] = None


class PatentItem(BaseModel):
    """专利"""
    name: Optional[str] = None
    patent_no: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    holder: Optional[str] = None
    inventors: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class ProfileUpdate(BaseModel):
    """更新画像（部分更新，整体替换各字段）"""
    basic_info: Optional[dict[str, Any]] = None
    education: Optional[list[dict[str, Any]]] = None
    experience: Optional[list[dict[str, Any]]] = None
    skills: Optional[list[str]] = None
    projects: Optional[list[dict[str, Any]]] = None
    summary: Optional[dict[str, Any]] = None
    certifications: Optional[list[dict[str, Any]]] = None
    job_intent: Optional[dict[str, Any]] = None
    languages: Optional[list[dict[str, Any]]] = None
    awards: Optional[list[dict[str, Any]]] = None
    essays: Optional[list[dict[str, Any]]] = None
    publications: Optional[list[dict[str, Any]]] = None
    patents: Optional[list[dict[str, Any]]] = None
    extra_fields: Optional[dict[str, Any]] = None


class ProfileResponse(BaseModel):
    """画像响应"""
    id: str
    user_id: str
    basic_info: Optional[dict[str, Any]] = None
    education: Optional[list] = None
    experience: Optional[list] = None
    skills: Optional[list] = None
    projects: Optional[list] = None
    summary: Optional[dict[str, Any]] = None
    certifications: Optional[list] = None
    job_intent: Optional[dict[str, Any]] = None
    languages: Optional[list] = None
    awards: Optional[list] = None
    essays: Optional[list] = None
    publications: Optional[list] = None
    patents: Optional[list] = None
    extra_fields: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
