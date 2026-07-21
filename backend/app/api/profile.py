"""
用户画像 API
提供用户画像的增删改查接口
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.profile import Profile

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


class BasicInfo(BaseModel):
    """基本信息"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth: Optional[str] = None
    # 注意：身份证号和家庭住址等敏感信息不应提交到服务器


class Education(BaseModel):
    """教育经历"""
    school: str
    major: str
    degree: str
    start_date: str
    end_date: str


class Experience(BaseModel):
    """工作经历"""
    company: str
    title: str
    start_date: str
    end_date: str
    description: str


class JobIntent(BaseModel):
    """求职意向"""
    role: str
    cities: List[str]
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_type: str = "全职"


class ProfileCreate(BaseModel):
    """创建用户画像"""
    basic_info: Optional[Dict[str, Any]] = {}
    education: Optional[List[Dict[str, Any]]] = []
    experience: Optional[List[Dict[str, Any]]] = []
    skills: Optional[List[str]] = []
    job_intent: Optional[Dict[str, Any]] = {}
    extra_fields: Optional[Dict[str, Any]] = {}


class ProfileUpdate(BaseModel):
    """更新用户画像"""
    basic_info: Optional[Dict[str, Any]] = None
    education: Optional[List[Dict[str, Any]]] = None
    experience: Optional[List[Dict[str, Any]]] = None
    skills: Optional[List[str]] = None
    job_intent: Optional[Dict[str, Any]] = None
    extra_fields: Optional[Dict[str, Any]] = None


@router.get("/")
async def get_profile(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户画像"""
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    
    if not profile:
        # 如果不存在，创建一个空的画像
        profile = Profile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    
    return {
        "code": 0,
        "message": "获取成功",
        "data": {
            "basic_info": profile.basic_info or {},
            "education": profile.education or [],
            "experience": profile.experience or [],
            "skills": profile.skills or [],
            "job_intent": profile.job_intent or {},
            "extra_fields": profile.extra_fields or {}
        }
    }


@router.post("/")
async def create_or_update_profile(
    profile_data: ProfileUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建或更新用户画像"""
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    
    if not profile:
        # 创建新画像
        profile = Profile(
            user_id=user_id,
            basic_info=profile_data.basic_info or {},
            education=profile_data.education or [],
            experience=profile_data.experience or [],
            skills=profile_data.skills or [],
            job_intent=profile_data.job_intent or {},
            extra_fields=profile_data.extra_fields or {}
        )
        db.add(profile)
    else:
        # 更新现有画像
        if profile_data.basic_info is not None:
            profile.basic_info = profile_data.basic_info
        if profile_data.education is not None:
            profile.education = profile_data.education
        if profile_data.experience is not None:
            profile.experience = profile_data.experience
        if profile_data.skills is not None:
            profile.skills = profile_data.skills
        if profile_data.job_intent is not None:
            profile.job_intent = profile_data.job_intent
        if profile_data.extra_fields is not None:
            profile.extra_fields = profile_data.extra_fields
    
    db.commit()
    db.refresh(profile)
    
    return {
        "code": 0,
        "message": "保存成功",
        "data": {
            "user_id": str(profile.user_id)
        }
    }


@router.delete("/")
async def delete_profile(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除用户画像"""
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户画像不存在"
        )
    
    db.delete(profile)
    db.commit()
    
    return {
        "code": 0,
        "message": "删除成功"
    }