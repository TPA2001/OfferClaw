"""
用户画像 Schema

定义用户画像相关的请求/响应 Pydantic 模型。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class BasicInfo(BaseModel):
    """基本信息（均为非敏感字段；身份证/住址/银行卡/护照等敏感字段不在此结构，仅本地存储）"""
    name: Optional[str] = None
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
    wechat: Optional[str] = None
    qq: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    english_level: Optional[str] = None
    driving_license: Optional[str] = None
    job_status: Optional[str] = None


class EducationItem(BaseModel):
    """教育经历"""
    school: Optional[str] = None
    major: Optional[str] = None
    degree: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ExperienceItem(BaseModel):
    """工作经历"""
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
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
    extra_fields: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
