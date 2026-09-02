"""
用户画像 API
提供用户画像的增删改查接口
"""

import json
import logging
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.llm import Message, get_gen_provider
from app.core.response import ok, NotFoundError, BadRequestError
from app.core.sanitizer import strip_sensitive_basic as _strip_sensitive_basic
from app.models.profile import Profile
from app.agent.memory.evolution import trigger_evolution

logger = logging.getLogger("offercabin.api.profile")

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


class BasicInfo(BaseModel):
    """基本信息"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth: Optional[str] = None
    # 注意：身份证号、家庭住址、银行卡、护照等敏感信息不应提交到服务器，
    # API 在落库前会再次剔除任何敏感 key（见 _strip_sensitive_basic）。


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
    skills: Optional[List[Dict[str, Any]]] = []
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
    skills: Optional[List[Dict[str, Any]]] = None
    projects: Optional[List[Dict[str, Any]]] = None
    summary: Optional[Dict[str, Any]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    job_intent: Optional[Dict[str, Any]] = None
    languages: Optional[List[Dict[str, Any]]] = None
    awards: Optional[List[Dict[str, Any]]] = None
    essays: Optional[List[Dict[str, Any]]] = None
    publications: Optional[List[Dict[str, Any]]] = None
    patents: Optional[List[Dict[str, Any]]] = None
    extra_fields: Optional[Dict[str, Any]] = None


class FieldDescriptor(BaseModel):
    """网页表单字段描述（来自浏览器插件）"""
    field_index: Optional[int] = None    # 前端定位用，原样回传
    type: str = "text"
    name: str = ""
    id: str = ""
    label: str = ""
    placeholder: str = ""
    ariaLabel: str = ""
    options: List[str] = []


class MatchFieldsRequest(BaseModel):
    """插件字段语义匹配请求（LLM 兜底）"""
    fields: List[FieldDescriptor] = []


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
            "languages": profile.languages or [],
            "awards": profile.awards or [],
            "essays": profile.essays or [],
            "publications": profile.publications or [],
            "patents": profile.patents or [],
            "extra_fields": profile.extra_fields or {}
        },
        message="获取成功",
    )


@router.post("/")
async def create_or_update_profile(
    profile_data: ProfileUpdate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建或更新用户画像"""
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()

    if not profile:
        # 创建新画像
        profile = Profile(
            user_id=user_id,
            basic_info=_strip_sensitive_basic(profile_data.basic_info or {}),
            education=profile_data.education or [],
            experience=profile_data.experience or [],
            skills=profile_data.skills or [],
            projects=profile_data.projects or [],
            summary=profile_data.summary or {},
            certifications=profile_data.certifications or [],
            job_intent=profile_data.job_intent or {},
            languages=profile_data.languages or [],
            awards=profile_data.awards or [],
            essays=profile_data.essays or [],
            publications=profile_data.publications or [],
            patents=profile_data.patents or [],
            extra_fields=profile_data.extra_fields or {}
        )
        db.add(profile)
    else:
        # 更新现有画像
        if profile_data.basic_info is not None:
            profile.basic_info = _strip_sensitive_basic(profile_data.basic_info)
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
        if profile_data.languages is not None:
            profile.languages = profile_data.languages
        if profile_data.awards is not None:
            profile.awards = profile_data.awards
        if profile_data.essays is not None:
            profile.essays = profile_data.essays
        if profile_data.publications is not None:
            profile.publications = profile_data.publications
        if profile_data.patents is not None:
            profile.patents = profile_data.patents
        if profile_data.extra_fields is not None:
            profile.extra_fields = profile_data.extra_fields

    db.commit()
    db.refresh(profile)

    # 画像演化：异步（后台）检测变更并提炼长期记忆，不阻塞主流程
    background_tasks.add_task(trigger_evolution, str(profile.user_id), "api")

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

    # 基本信息（拓展后的标准字段）
    b = profile.basic_info or {}
    basic_keys = [
        "name", "gender", "birth", "phone", "email", "location",
        "ethnicity", "political_status", "marital_status", "native_place",
        "household_type", "height", "weight", "health",
        "wechat", "qq", "website", "github", "linkedin",
        "english_level", "driving_license", "job_status",
        "english_name", "current_company", "current_title",
        "years_of_experience", "highest_education", "available_date",
    ]
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
    # 兼容旧字段名：self_eval/advantage ↔ self_intro/strengths
    summary_keys = ["self_intro", "strengths", "career_goal"]
    summary_filled = sum(1 for k in summary_keys if s.get(k)
                         or (k == "self_intro" and s.get("self_eval"))
                         or (k == "strengths" and s.get("advantage")))
    sections["summary"] = {
        "total": len(summary_keys), "filled": summary_filled,
        "percentage": round(summary_filled / len(summary_keys) * 100) if summary_keys else 0,
        "missing": [k for k in summary_keys if not (s.get(k)
                    or (k == "self_intro" and s.get("self_eval"))
                    or (k == "strengths" and s.get("advantage")))],
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

    # 语言能力
    lang_count = len(profile.languages or [])
    sections["languages"] = {
        "total": 1, "filled": 1 if lang_count > 0 else 0,
        "percentage": 100 if lang_count > 0 else 0,
        "count": lang_count,
    }

    # 获奖/荣誉
    award_count = len(profile.awards or [])
    sections["awards"] = {
        "total": 1, "filled": 1 if award_count > 0 else 0,
        "percentage": 100 if award_count > 0 else 0,
        "count": award_count,
    }

    # 开放题答案库
    essay_count = len(profile.essays or [])
    sections["essays"] = {
        "total": 1, "filled": 1 if essay_count > 0 else 0,
        "percentage": 100 if essay_count > 0 else 0,
        "count": essay_count,
    }

    # 论文/发表物
    pub_count = len(profile.publications or [])
    sections["publications"] = {
        "total": 1, "filled": 1 if pub_count > 0 else 0,
        "percentage": 100 if pub_count > 0 else 0,
        "count": pub_count,
    }

    # 专利
    pat_count = len(profile.patents or [])
    sections["patents"] = {
        "total": 1, "filled": 1 if pat_count > 0 else 0,
        "percentage": 100 if pat_count > 0 else 0,
        "count": pat_count,
    }

    # 求职意向
    j = profile.job_intent or {}
    intent_keys = ["role", "cities", "salary_min", "salary_max", "target_positions", "target_cities"]
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
        "basic_info": 16, "education": 12, "experience": 16, "skills": 8,
        "projects": 10, "summary": 5, "certifications": 4, "languages": 4,
        "awards": 5, "essays": 4, "publications": 4, "patents": 3, "job_intent": 9,
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
    flat["english_name"] = b.get("english_name", "")
    flat["phone"] = b.get("phone", "")
    flat["email"] = b.get("email", "")
    flat["gender"] = b.get("gender", "")
    flat["birth"] = b.get("birth", "")
    flat["age"] = b.get("age", "")
    flat["location"] = b.get("location", "")
    flat["ethnicity"] = b.get("ethnicity", "")
    flat["political_status"] = b.get("political_status", "")
    flat["marital_status"] = b.get("marital_status", "")
    flat["native_place"] = b.get("native_place", "")
    flat["household_type"] = b.get("household_type", "")
    flat["height"] = b.get("height", "")
    flat["weight"] = b.get("weight", "")
    flat["health"] = b.get("health", "")
    flat["wechat"] = b.get("wechat", "")
    flat["qq"] = b.get("qq", "")
    flat["website"] = b.get("website", "")
    flat["github"] = b.get("github", "")
    flat["linkedin"] = b.get("linkedin", "")
    flat["english_level"] = b.get("english_level", "")
    flat["driving_license"] = b.get("driving_license", "")
    flat["job_status"] = b.get("job_status", "")
    flat["current_company"] = b.get("current_company", "")
    flat["current_title"] = b.get("current_title", "")
    flat["years_of_experience"] = b.get("years_of_experience", "")
    flat["highest_education"] = b.get("highest_education", "")
    flat["available_date"] = b.get("available_date", "")

    # 求职意向
    j = profile.job_intent or {}
    flat["intent_role"] = j.get("role", "") or (j.get("target_positions") or [""])[0]
    flat["intent_cities"] = j.get("cities", []) or j.get("target_cities", [])
    flat["intent_salary_min"] = j.get("salary_min", "") or j.get("expected_salary", "")
    flat["intent_salary_max"] = j.get("salary_max", "")
    flat["intent_job_type"] = j.get("job_type", "") or j.get("work_type", "")
    flat["target_positions"] = j.get("target_positions", [])
    flat["target_cities"] = j.get("target_cities", [])
    flat["expected_salary"] = j.get("expected_salary", "")
    flat["work_type"] = j.get("work_type", "")
    flat["availability"] = j.get("availability", "") or j.get("notice_period", "")
    flat["expected_industry"] = j.get("target_industry", "") or j.get("expected_industry", "")
    flat["target_level"] = j.get("target_level", "")
    flat["remote_preference"] = j.get("remote_preference", "")
    flat["willing_to_relocate"] = j.get("willing_to_relocate", "")
    flat["willing_to_travel"] = j.get("willing_to_travel", "")
    flat["current_salary"] = j.get("current_salary", "")

    # 教育（取最近一条 / 最高学历）
    edus = profile.education or []
    if edus:
        latest = edus[-1]
        flat["latest_school"] = latest.get("school", "")
        flat["latest_major"] = latest.get("major", "")
        flat["latest_degree"] = latest.get("degree", "")
        flat["latest_school_type"] = latest.get("school_type", "")
        flat["latest_edu_form"] = latest.get("edu_form", "")
        flat["latest_courses"] = latest.get("courses", "")
        flat["latest_edu_start"] = latest.get("start_date", "")
        flat["latest_edu_end"] = latest.get("end_date", "")
    else:
        flat["latest_school"] = ""
        flat["latest_major"] = ""
        flat["latest_degree"] = ""
        flat["latest_school_type"] = ""
        flat["latest_edu_form"] = ""
        flat["latest_courses"] = ""
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
    # 技能可能是字符串，也可能是 {name, level, category} 对象（Web 端格式）
    skill_names = [
        (s.get("name") if isinstance(s, dict) else str(s)) for s in skills
    ]
    flat["skills_str"] = "、".join(filter(None, skill_names))

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

    # 自我评价（兼容旧字段名）
    s = profile.summary or {}
    flat["self_eval"] = s.get("self_intro", "") or s.get("self_eval", "")
    flat["advantage"] = s.get("strengths", "") or s.get("advantage", "")
    flat["self_intro"] = flat["self_eval"]
    flat["strengths"] = flat["advantage"]
    flat["career_goal"] = s.get("career_goal", "")

    # 证书
    certs = profile.certifications or []
    flat["all_certs"] = "、".join(filter(None, [c.get("name", "") for c in certs]))

    # 语言能力
    langs = profile.languages or []
    flat["languages"] = langs
    flat["languages_str"] = "、".join(
        filter(None, [
            (l.get("name", "") + (" " + l.get("proficiency", ""))).strip() for l in langs
        ])
    )

    # 获奖/荣誉
    awards = profile.awards or []
    flat["awards"] = awards
    flat["all_awards"] = "、".join(filter(None, [a.get("name", "") for a in awards]))

    # 开放题答案库（含多版本标签）
    essays = profile.essays or []
    flat["essays"] = essays
    flat["essay_count"] = len(essays)

    # 论文/发表物
    pubs = profile.publications or []
    flat["publications"] = pubs
    flat["all_publications"] = "、".join(filter(None, [p.get("title", "") for p in pubs]))
    flat["publication_count"] = len(pubs)

    # 专利
    pats = profile.patents or []
    flat["patents"] = pats
    flat["all_patents"] = "、".join(filter(None, [p.get("name", "") for p in pats]))
    flat["patent_count"] = len(pats)

    # 自定义字段
    extra = profile.extra_fields or {}
    for k, v in extra.items():
        flat[f"extra_{k}"] = v

    return ok(flat, message="获取成功")


@router.post("/match-fields")
async def match_fields(
    req: MatchFieldsRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    插件字段语义匹配（LLM 兜底）

    浏览器插件规则匹配未命中的字段，提交到这里用 LLM 做语义匹配，
    返回 [{field_index, key, value, confidence, reason}]。
    key 对应插件 lib/profile.js 的标准字段 key（如 name / gender / school …）。

    未配置 LLM 时返回空 mappings（插件自然回退到本地规则匹配，不影响填写）。
    """
    if not req.fields:
        return ok({"mappings": [], "source": "empty"})

    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        return ok({"mappings": [], "source": "no_profile"})

    flat = _build_match_profile(profile)

    try:
        provider = get_gen_provider()
        if getattr(provider, "name", "") == "mock":
            return ok({"mappings": [], "source": "mock"})
    except Exception as exc:  # 未配置 LLM 等任何异常都优雅降级
        logger.info(f"match-fields LLM 不可用，跳过兜底: {exc}")
        return ok({"mappings": [], "source": "unavailable"})

    fields_payload = []
    for i, f in enumerate(req.fields):
        ctx = {
            "index": i,
            "label": f.label,
            "placeholder": f.placeholder,
            "aria_label": f.ariaLabel,
            "name": f.name,
            "id": f.id,
            "type": f.type,
            "options": f.options or [],
        }
        # 去掉空上下文
        ctx = {k: v for k, v in ctx.items() if v}
        fields_payload.append(ctx)

    system = (
        "你是网申表单自动填写助手。给定网页表单字段列表和用户简历画像字典，"
        "判断每个字段应该用画像中的哪个 key 的值来填。"
        "画像 key 只能从提供的画像字典的 key 中选择；"
        "只有置信度较高时才返回映射，否则 confidence 低于 0.6 或无法判断就返回 confidence 0 并 reason 说明。"
        '只输出 JSON 数组，不要输出任何解释或 markdown：'
        '[{"index": 0, "key": "name", "confidence": 0.95, "reason": "label 为姓名"}]'
    )
    user = (
        "画像字段（key: 值）：\n"
        + json.dumps(flat, ensure_ascii=False, indent=1)
        + "\n\n表单字段：\n"
        + json.dumps(fields_payload, ensure_ascii=False, indent=1)
        + "\n\n请返回 JSON 数组。"
    )

    try:
        resp = await provider.chat(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.1,
            max_tokens=1200,
        )
        raw = (resp.content or "").strip()
        arr = _parse_json_array(raw)
    except Exception as exc:  # LLM 调用失败不阻断
        logger.warning(f"match-fields LLM 调用失败: {exc}")
        return ok({"mappings": [], "source": "error"})

    mappings = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        key = str(item.get("key", "")).strip()
        if not isinstance(idx, int) or idx < 0 or idx >= len(req.fields):
            continue
        if key not in flat:
            continue
        confidence = float(item.get("confidence", 0) or 0)
        if confidence < 0.6:
            continue
        mappings.append({
            "fieldIndex": idx,
            "key": key,
            "value": str(flat.get(key, "") or ""),
            "confidence": round(confidence, 2),
            "reason": str(item.get("reason", "") or ""),
        })

    return ok({"mappings": mappings, "source": "llm"})


def _build_match_profile(profile: Profile) -> Dict[str, Any]:
    """把画像压成非空扁平字典，供 match-fields 的 LLM 提示使用"""
    flat: Dict[str, Any] = {}
    b = profile.basic_info or {}

    text_keys = [
        "name", "english_name", "phone", "email", "gender", "birth", "age",
        "location", "ethnicity", "political_status", "marital_status",
        "native_place", "household_type", "household_location", "height",
        "weight", "wechat", "qq", "website", "github", "linkedin",
        "job_status", "current_company", "current_title", "years_of_experience",
        "highest_education", "available_date",
    ]
    for k in text_keys:
        v = b.get(k)
        if v:
            flat[k] = v

    # 教育（最近一条 + 全部汇总）
    edus = profile.education or []
    if edus:
        latest = edus[-1]
        for k in ("school", "major", "degree", "school_type", "edu_form", "gpa", "ranking"):
            if latest.get(k):
                flat[k] = latest.get(k)
        if latest.get("start_date"):
            flat["edu_start"] = latest["start_date"]
        if latest.get("end_date"):
            flat["edu_end"] = latest["end_date"]
    flat["education_summary"] = "；".join(filter(None, [
        " / ".join(filter(None, [e.get("school", ""), e.get("major", ""), e.get("degree", "")]))
        for e in edus
    ]))

    # 工作（最近一条 + 全部汇总）
    exps = profile.experience or []
    if exps:
        latest = exps[-1]
        if latest.get("company"):
            flat.setdefault("current_company", latest["company"])
        if latest.get("title"):
            flat.setdefault("current_title", latest["title"])
    flat["experience_summary"] = "；".join(filter(None, [
        " / ".join(filter(None, [e.get("company", ""), e.get("title", ""), e.get("start_date", ""), e.get("end_date", "")]))
        for e in exps
    ]))

    # 项目
    projs = profile.projects or []
    flat["project_summary"] = "；".join(filter(None, [
        " / ".join(filter(None, [p.get("name", ""), p.get("role", ""), p.get("description", "")]))
        for p in projs
    ]))

    # 技能
    skills = profile.skills or []
    skill_names = [s.get("name") if isinstance(s, dict) else str(s) for s in skills]
    if skill_names:
        flat["skills_str"] = "、".join(filter(None, skill_names))

    # 自我评价
    s = profile.summary or {}
    if s.get("self_intro") or s.get("self_eval"):
        flat["self_intro"] = s.get("self_intro") or s.get("self_eval")
    if s.get("strengths") or s.get("advantage"):
        flat["strengths"] = s.get("strengths") or s.get("advantage")
    if s.get("career_goal"):
        flat["career_goal"] = s["career_goal"]

    # 证书 / 语言 / 获奖 / 论文 / 专利
    certs = profile.certifications or []
    if certs:
        flat["certifications_str"] = "、".join(filter(None, [c.get("name", "") for c in certs]))
    langs = profile.languages or []
    if langs:
        flat["languages_str"] = "、".join(filter(None, [l.get("name", "") for l in langs]))
    awards = profile.awards or []
    if awards:
        flat["awards_str"] = "、".join(filter(None, [a.get("name", "") for a in awards]))
    pubs = profile.publications or []
    if pubs:
        flat["publications_str"] = "、".join(filter(None, [p.get("title", "") for p in pubs]))
    pats = profile.patents or []
    if pats:
        flat["patents_str"] = "、".join(filter(None, [p.get("name", "") for p in pats]))

    # 求职意向
    j = profile.job_intent or {}
    if j.get("role"):
        flat["intent_role"] = j["role"]
    elif j.get("target_positions"):
        flat["intent_role"] = j["target_positions"][0]
    cities = j.get("cities") or j.get("target_cities") or []
    if cities:
        flat["intent_city"] = "、".join(cities)
    if j.get("expected_salary"):
        flat["intent_salary"] = j["expected_salary"]
    if j.get("salary_min"):
        flat["intent_salary"] = j["salary_min"]
    if j.get("job_type") or j.get("work_type"):
        flat["job_type"] = j.get("job_type") or j.get("work_type")
    if j.get("availability") or j.get("notice_period"):
        flat["availability"] = j.get("availability") or j.get("notice_period")
    if j.get("target_industry"):
        flat["target_industry"] = j["target_industry"]

    # 紧急联系人（若本地补充了 non-sensitive 描述）
    extra = profile.extra_fields or {}
    if extra.get("emergency_contact"):
        flat["emergency_contact"] = extra["emergency_contact"]
    if extra.get("emergency_phone"):
        flat["emergency_phone"] = extra["emergency_phone"]

    return flat


def _parse_json_array(raw: str) -> List[Any]:
    """从 LLM 输出中解析 JSON 数组（容忍 ```json 代码块 / 前后缀文字）"""
    if not raw:
        return []
    text = raw.strip()
    # 去掉 markdown 代码块围栏
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # 尝试直接解析
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        pass
    # 抽取第一个 [ ... ] 片段
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


@router.post("/import-pdf")
async def import_pdf_resume(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """从 PDF 简历解析画像（不直接保存，返回结构化数据供前端确认后保存）

    解析策略：
    - pdfplumber 提取文本（本地，非 LLM）
    - 优先 LLM 结构化（用户已配置 Key），否则规则降级
    - 敏感字段（身份证/住址）后端不存储，解析结果也不含这些
    """
    from app.services.resume_parser import parse_resume

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise BadRequestError("仅支持 PDF 文件")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise BadRequestError("PDF 文件为空")
    # 防超大文件导致内存压力（20MB 上限，正常简历远小于此）
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise BadRequestError("PDF 文件过大（最大 20MB）")

    profile, text, source = await parse_resume(pdf_bytes)
    source_label = {"llm": "LLM", "rules": "规则", "empty": "空", "error": "失败"}.get(source, source)
    return ok(
        {
            "profile": profile,
            "source": source,
            "text_length": len(text),
            "text_preview": text[:500] if text else "",
        },
        message=f"PDF 解析完成（{source_label}）",
    )


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