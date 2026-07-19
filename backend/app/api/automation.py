"""
智能填写 API
提供表单字段提取、匹配、填写的 HTTP 接口
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

from app.core.auth import get_current_user
from app.automation import FormExtractor, FormFiller, FieldMatcher

logger = logging.getLogger("offerclaw.automation")

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class ExtractRequest(BaseModel):
    """字段提取请求"""
    html_content: str = None  # HTML 内容（可选）
    url: str = None  # 页面 URL（可选，需要浏览器扩展提供）


class ExtractResponse(BaseModel):
    """字段提取响应"""
    fields: List[Dict[str, Any]]
    count: int


class MatchRequest(BaseModel):
    """字段匹配请求"""
    fields: List[Dict[str, Any]]
    user_id: str


class MatchResponse(BaseModel):
    """字段匹配响应"""
    mappings: List[Dict[str, Any]]
    profile_used: bool


class FillRequest(BaseModel):
    """表单填写请求"""
    fields: List[Dict[str, Any]]
    mappings: List[Dict[str, Any]]
    sensitive_data: Optional[Dict[str, str]] = None


@router.post("/extract", response_model=ExtractResponse)
async def extract_fields(
    request: ExtractRequest,
    user_id: str = Depends(get_current_user),
):
    """
    提取页面表单字段

    注意：此接口通常由浏览器扩展调用，提供字段列表。
    如果传入 html_content，会尝试从中提取字段。
    """
    logger.info(f"用户 {user_id} 请求提取表单字段")

    # 如果没有提供 HTML，返回空列表（前端应该已经提取）
    if not request.html_content:
        return ExtractResponse(fields=[], count=0)

    # TODO: 实现 HTML 解析和字段提取
    # 这里需要集成 Playwright 或者使用 BeautifulSoup 解析 HTML
    # 暂时返回空列表
    logger.warning("HTML 解析功能待实现")

    return ExtractResponse(fields=[], count=0)


@router.post("/match", response_model=MatchResponse)
async def match_fields(
    request: MatchRequest,
    user_id: str = Depends(get_current_user),
):
    """
    字段语义匹配

    接收表单字段列表，返回与用户画像的匹配结果。
    """
    logger.info(f"用户 {user_id} 请求字段匹配，字段数: {len(request.fields)}")

    try:
        from app.core.database import SessionLocal
        from app.models.profile import Profile

        # 从数据库加载用户画像
        db = SessionLocal()
        try:
            profile = db.query(Profile).filter(Profile.user_id == user_id).first()
            if not profile:
                profile_data = {}
            else:
                profile_data = {
                    "basic_info": profile.basic_info or {},
                    "education": profile.education or [],
                    "experience": profile.experience or [],
                    "skills": profile.skills or [],
                    "job_intent": profile.job_intent or {},
                }

            # 执行匹配
            matcher = FieldMatcher()
            result = await matcher.match(
                fields=request.fields,
                user_id=user_id,
                profile=profile_data,
                db=db
            )

            return MatchResponse(
                mappings=result["mappings"],
                profile_used=result["profile_used"]
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"字段匹配失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"字段匹配失败: {str(e)}"
        )


@router.post("/fill")
async def fill_form(
    request: FillRequest,
    user_id: str = Depends(get_current_user),
):
    """
    执行表单填写

    接收字段列表和匹配结果，返回填写指令供浏览器扩展执行。
    """
    logger.info(f"用户 {user_id} 请求表单填写，字段数: {len(request.fields)}")

    # 返回填写指令（浏览器扩展会执行）
    return {
        "code": 0,
        "message": "填写指令已生成",
        "data": {
            "fields": request.fields,
            "mappings": request.mappings,
            "sensitive_data": request.sensitive_data or {}
        }
    }


@router.get("/status")
async def get_automation_status():
    """获取智能填写模块状态"""
    return {
        "code": 0,
        "message": "智能填写模块运行正常",
        "data": {
            "form_extractor": "available",
            "form_filler": "available",
            "field_matcher": "available"
        }
    }