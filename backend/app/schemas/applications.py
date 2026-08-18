"""
投递记录 Schema

定义投递管理相关的请求/响应 Pydantic 模型。
从 app/api/applications.py 中提取，集中管理。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ===== 请求 Schema =====

class ApplicationCreate(BaseModel):
    """创建投递记录"""
    company: str = Field(..., min_length=1, max_length=200, description="公司名称")
    position: str = Field(..., min_length=1, max_length=200, description="岗位名称")
    job_url: Optional[str] = None
    source: Optional[str] = Field(None, max_length=50, description="来源：boss/直聘/官网/内推/校招")
    status: str = Field("applied", description="初始状态")
    priority: str = Field("medium", description="优先级：high/medium/low")
    notes: Optional[str] = None
    tags: Optional[str] = None
    # 细化字段
    rejection_stage: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[datetime] = None
    assessment_deadline: Optional[datetime] = None
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[datetime] = None
    hr_contact: Optional[str] = None


class ApplicationUpdate(BaseModel):
    """更新投递记录（部分更新）"""
    company: Optional[str] = None
    position: Optional[str] = None
    job_url: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    rejection_stage: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[datetime] = None
    assessment_deadline: Optional[datetime] = None
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[datetime] = None
    hr_contact: Optional[str] = None


class ApplicationStatusUpdate(BaseModel):
    """快速更新状态"""
    status: str = Field(..., description="新状态")
    note: Optional[str] = None


class ApplicationBatchImport(BaseModel):
    """批量导入"""
    applications: list[ApplicationCreate]


# ===== 响应 Schema =====

class ApplicationResponse(BaseModel):
    """投递记录响应"""
    id: str
    company: str
    position: str
    job_url: Optional[str] = None
    source: Optional[str] = None
    status: str
    priority: str = "medium"
    notes: Optional[str] = None
    tags: Optional[str] = None
    rejection_stage: Optional[str] = None
    interview_round: Optional[int] = None
    next_interview_at: Optional[datetime] = None
    assessment_deadline: Optional[datetime] = None
    offer_status: Optional[str] = None
    offer_salary: Optional[str] = None
    offer_location: Optional[str] = None
    offer_deadline: Optional[datetime] = None
    hr_contact: Optional[str] = None
    status_history: Optional[list] = None
    applied_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    """投递列表响应"""
    applications: list[ApplicationResponse]
    total: int
