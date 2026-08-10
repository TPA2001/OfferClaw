"""
用户画像 API
提供用户画像的增删改查接口
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.response import ok, NotFoundError
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
    projects: Optional[List[Dict[str, Any]]] = []
    summary: Optional[Dict[str, Any]] = {}
    certifications: Optional[List[Dict[str, Any]]] = []
    job_intent: Optional[Dict[str, Any]] = {}
    extra_fields: Optional[Dict[str, Any]] = {}


class ProfileUpdate(BaseModel):
    """更新用户画像"""
    basic_info: Optional[Dict[str, Any]] = None
    education: Optional[List[Dict[str, Any]]] = None
    experience: Optional[List[Dict[str, Any]]] = None
    skills: Optional[List[str]] = None
    projects: Optional[List[Dict[str, Any]]] = None
    summary: Optional[Dict[str, Any]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
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
    
    return ok(
        {
            "basic_info": profile.basic_info or {},
            "education": profile.education or [],
            "experience": profile.experience or [],
            "skills": profile.skills or [],
            "projects": profile.projects or [],
            "summary": profile.summary or {},
            "certifications": profile.certifications or [],
            "job_intent": profile.job_intent or {},
            "extra_fields": profile.extra_fields or {}
        },
        message="获取成功",
    )


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
            projects=profile_data.projects or [],
            summary=profile_data.summary or {},
            certifications=profile_data.certifications or [],
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
        if profile_data.projects is not None:
            profile.projects = profile_data.projects
        if profile_data.summary is not None:
            profile.summary = profile_data.summary
        if profile_data.certifications is not None:
            profile.certifications = profile_data.certifications
        if profile_data.job_intent is not None:
            profile.job_intent = profile_data.job_intent
        if profile_data.extra_fields is not None:
            profile.extra_fields = profile_data.extra_fields

    db.commit()
    db.refresh(profile)

    return ok(
        {"user_id": str(profile.user_id)},
        message="保存成功",
    )


@router.delete("/")
async def delete_profile(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除用户画像"""
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()

    if not profile:
        raise NotFoundError("用户画像不存在")

    db.delete(profile)
    db.commit()

    return ok(None, message="删除成功")


@router.get("/completion")
async def get_profile_completion(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取画像完成度详情

    返回各区块的填写状态和总体完成度百分比，引导用户补全信息。
    """
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        return ok(
            {"percentage": 0, "sections": {}, "missing": ["all"]},
            message="画像为空",
        )

    sections = {}
    missing = []

    # 基本信息（5 个字段）
    b = profile.basic_info or {}
    basic_keys = ["name", "phone", "email", "gender", "birth"]
    basic_filled = sum(1 for k in basic_keys if b.get(k))
    sections["basic_info"] = {
        "total": len(basic_keys), "filled": basic_filled,
        "percentage": round(basic_filled / len(basic_keys) * 100) if basic_keys else 0,
        "missing": [k for k in basic_keys if not b.get(k)],
    }
    if basic_filled < len(basic_keys):
        missing.append("basic_info")

    # 教育
    edu_count = len(profile.education or [])
    sections["education"] = {
        "total": 1, "filled": 1 if edu_count > 0 else 0,
        "percentage": 100 if edu_count > 0 else 0,
        "count": edu_count,
    }
    if edu_count == 0:
        missing.append("education")

    # 工作经历
    exp_count = len(profile.experience or [])
    sections["experience"] = {
        "total": 1, "filled": 1 if exp_count > 0 else 0,
        "percentage": 100 if exp_count > 0 else 0,
        "count": exp_count,
    }
    if exp_count == 0:
        missing.append("experience")

    # 技能
    skill_count = len(profile.skills or [])
    sections["skills"] = {
        "total": 1, "filled": 1 if skill_count >= 3 else 0,
        "percentage": min(100, round(skill_count / 3 * 100)) if skill_count else 0,
        "count": skill_count,
    }
    if skill_count < 3:
        missing.append("skills")

    # 项目经历
    proj_count = len(profile.projects or [])
    sections["projects"] = {
        "total": 1, "filled": 1 if proj_count > 0 else 0,
        "percentage": 100 if proj_count > 0 else 0,
        "count": proj_count,
    }
    if proj_count == 0:
        missing.append("projects")

    # 自我评价
    s = profile.summary or {}
    summary_keys = ["self_eval", "advantage", "career_goal"]
    summary_filled = sum(1 for k in summary_keys if s.get(k))
    sections["summary"] = {
        "total": len(summary_keys), "filled": summary_filled,
        "percentage": round(summary_filled / len(summary_keys) * 100) if summary_keys else 0,
        "missing": [k for k in summary_keys if not s.get(k)],
    }
    if summary_filled == 0:
        missing.append("summary")

    # 证书
    cert_count = len(profile.certifications or [])
    sections["certifications"] = {
        "total": 1, "filled": 1 if cert_count > 0 else 0,
        "percentage": 100 if cert_count > 0 else 0,
        "count": cert_count,
    }

    # 求职意向
    j = profile.job_intent or {}
    intent_keys = ["role", "cities", "salary_min", "salary_max"]
    intent_filled = sum(1 for k in intent_keys if j.get(k))
    sections["job_intent"] = {
        "total": len(intent_keys), "filled": intent_filled,
        "percentage": round(intent_filled / len(intent_keys) * 100) if intent_keys else 0,
        "missing": [k for k in intent_keys if not j.get(k)],
    }
    if intent_filled < 2:
        missing.append("job_intent")

    # 加权总完成度（基本信息权重最高）
    weights = {
        "basic_info": 25, "education": 15, "experience": 20, "skills": 10,
        "projects": 10, "summary": 5, "certifications": 5, "job_intent": 10,
    }
    total_pct = sum(sections[k]["percentage"] * weights[k] / 100 for k in weights)
    total_pct = round(total_pct)

    return ok(
        {
            "percentage": total_pct,
            "sections": sections,
            "missing": missing,
        },
        message="获取完成度成功",
    )


@router.get("/flatten")
async def get_profile_flatten(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取画像的扁平化字典（用于规则匹配 / 前端快速填充预览）

    把所有嵌套结构拍平成 key-value 字典，方便字段匹配时直接查找。
    """
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        return ok({}, message="画像为空")

    flat: Dict[str, Any] = {}

    # 基本信息
    b = profile.basic_info or {}
    flat["name"] = b.get("name", "")
    flat["phone"] = b.get("phone", "")
    flat["email"] = b.get("email", "")
    flat["gender"] = b.get("gender", "")
    flat["birth"] = b.get("birth", "")

    # 求职意向
    j = profile.job_intent or {}
    flat["intent_role"] = j.get("role", "")
    flat["intent_cities"] = j.get("cities", [])
    flat["intent_salary_min"] = j.get("salary_min", "")
    flat["intent_salary_max"] = j.get("salary_max", "")
    flat["intent_job_type"] = j.get("job_type", "")

    # 教育（取最近一条 / 最高学历）
    edus = profile.education or []
    if edus:
        latest = edus[-1]
        flat["latest_school"] = latest.get("school", "")
        flat["latest_major"] = latest.get("major", "")
        flat["latest_degree"] = latest.get("degree", "")
        flat["latest_edu_start"] = latest.get("start_date", "")
        flat["latest_edu_end"] = latest.get("end_date", "")
    else:
        flat["latest_school"] = ""
        flat["latest_major"] = ""
        flat["latest_degree"] = ""
        flat["latest_edu_start"] = ""
        flat["latest_edu_end"] = ""

    # 所有学历汇总字符串
    flat["all_degrees"] = "、".join(filter(None, [e.get("degree", "") for e in edus]))
    flat["all_schools"] = "、".join(filter(None, [e.get("school", "") for e in edus]))

    # 工作经历（取最近一条 / 当前职位）
    exps = profile.experience or []
    if exps:
        latest_exp = exps[-1]
        flat["latest_company"] = latest_exp.get("company", "")
        flat["latest_title"] = latest_exp.get("title", "")
        flat["latest_exp_start"] = latest_exp.get("start_date", "")
        flat["latest_exp_end"] = latest_exp.get("end_date", "")
        flat["latest_exp_desc"] = latest_exp.get("description", "")
    else:
        for k in ["latest_company", "latest_title", "latest_exp_start", "latest_exp_end", "latest_exp_desc"]:
            flat[k] = ""

    # 工作经历汇总
    flat["all_companies"] = "、".join(filter(None, [e.get("company", "") for e in exps]))
    flat["all_titles"] = "、".join(filter(None, [e.get("title", "") for e in exps]))
    flat["total_exp_years"] = _calc_exp_years(exps)

    # 技能
    skills = profile.skills or []
    flat["skills"] = skills
    flat["skills_str"] = "、".join(skills)

    # 项目经历
    projs = profile.projects or []
    if projs:
        latest_proj = projs[-1]
        flat["latest_project"] = latest_proj.get("name", "")
        flat["latest_project_role"] = latest_proj.get("role", "")
        flat["latest_project_desc"] = latest_proj.get("description", "")
        # tech_stack 兼容字符串和列表两种格式
        ts = latest_proj.get("tech_stack", "")
        if isinstance(ts, list):
            flat["latest_project_stack"] = "、".join(filter(None, [str(t) for t in ts]))
        else:
            flat["latest_project_stack"] = str(ts) if ts else ""
    else:
        for k in ["latest_project", "latest_project_role", "latest_project_desc", "latest_project_stack"]:
            flat[k] = ""
    flat["all_projects"] = "、".join(filter(None, [p.get("name", "") for p in projs]))

    # 自我评价
    s = profile.summary or {}
    flat["self_eval"] = s.get("self_eval", "")
    flat["advantage"] = s.get("advantage", "")
    flat["career_goal"] = s.get("career_goal", "")

    # 证书
    certs = profile.certifications or []
    flat["all_certs"] = "、".join(filter(None, [c.get("name", "") for c in certs]))

    # 自定义字段
    extra = profile.extra_fields or {}
    for k, v in extra.items():
        flat[f"extra_{k}"] = v

    return ok(flat, message="获取成功")


def _calc_exp_years(exps: list) -> str:
    """根据工作经历的起止时间估算工作年限"""
    if not exps:
        return "0"
    import re
    from datetime import datetime
    total_months = 0
    for e in exps:
        start = e.get("start_date", "")
        end = e.get("end_date", "")
        if not start:
            continue
        try:
            sy, sm = re.match(r"(\d{4})-(\d{1,2})", start).groups()[:2]
            if end and end != "至今":
                ey, em = re.match(r"(\d{4})-(\d{1,2})", end).groups()[:2]
            else:
                now = datetime.now()
                ey, em = str(now.year), str(now.month)
            months = (int(ey) - int(sy)) * 12 + (int(em) - int(sm))
            if months > 0:
                total_months += months
        except Exception:
            continue
    years = total_months / 12
    if years >= 1:
        return f"{years:.1f}年"
    return f"{total_months}个月"