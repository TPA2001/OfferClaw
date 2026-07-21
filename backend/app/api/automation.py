"""
智能填写 API
提供表单字段提取、匹配、填写的 HTTP 接口
支持 Web 版本（无需插件）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import asyncio

from app.core.auth import get_current_user
from app.services.smart_fill import get_smart_fill_service
from app.automation import FieldMatcher
from app.core.database import SessionLocal
from app.models.profile import Profile

logger = logging.getLogger("offerclaw.automation")

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class ExtractFromURLRequest(BaseModel):
    """从 URL 提取字段请求"""
    url: str


class MatchRequest(BaseModel):
    """字段匹配请求"""
    fields: List[Dict[str, Any]]


class GenerateScriptRequest(BaseModel):
    """生成填写脚本请求"""
    fields: List[Dict[str, Any]]
    mappings: List[Dict[str, Any]]


@router.post("/extract-from-url")
async def extract_from_url(
    request: ExtractFromURLRequest,
    user_id: str = Depends(get_current_user)
):
    """
    从 URL 提取表单字段（Web 版本，无需插件）
    
    流程：
    1. 用户输入目标 URL
    2. 系统后台抓取页面
    3. 自动识别表单字段
    4. 返回字段列表和页面信息
    """
    logger.info(f"用户 {user_id} 请求从 URL 提取字段: {request.url}")
    
    try:
        # 使用智能填写服务抓取页面
        service = get_smart_fill_service()
        result = await service.extract_fields_from_url(request.url)
        
        return {
            "code": 0,
            "message": "提取成功",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"字段提取失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"字段提取失败: {str(e)}"
        )


@router.post("/match")
async def match_fields(
    request: MatchRequest,
    user_id: str = Depends(get_current_user)
):
    """
    字段语义匹配（基于用户画像）
    
    流程：
    1. 接收表单字段列表
    2. 从数据库加载用户画像
    3. 使用 LLM 进行语义匹配
    4. 返回匹配结果
    """
    logger.info(f"用户 {user_id} 请求字段匹配，字段数: {len(request.fields)}")
    
    try:
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
            
            return {
                "code": 0,
                "message": "匹配成功",
                "data": {
                    "mappings": result["mappings"],
                    "profile_used": result["profile_used"]
                }
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"字段匹配失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"字段匹配失败: {str(e)}"
        )


@router.post("/generate-script")
async def generate_fill_script(
    request: GenerateScriptRequest,
    user_id: str = Depends(get_current_user)
):
    """
    生成填写脚本（用户复制到浏览器控制台执行）
    
    流程：
    1. 接收字段列表和匹配结果
    2. 生成 JavaScript 填写脚本
    3. 用户复制到浏览器控制台执行
    """
    logger.info(f"用户 {user_id} 请求生成填写脚本")
    
    try:
        # 生成填写脚本
        script = _generate_fill_script(request.fields, request.mappings)
        
        return {
            "code": 0,
            "message": "脚本生成成功",
            "data": {
                "script": script,
                "usage": "请将上述脚本复制到浏览器控制台（按 F12 打开）并执行"
            }
        }
        
    except Exception as e:
        logger.error(f"脚本生成失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"脚本生成失败: {str(e)}"
        )


def _generate_fill_script(fields: List[Dict], mappings: List[Dict]) -> str:
    """生成填写脚本"""
    script_lines = [
        "// OfferClaw 智能填写脚本",
        "// 请在目标页面打开控制台（按 F12）并执行此脚本",
        "",
        "(function() {",
        "  'use strict';",
        "",
        "  const fillData = {"
    ]
    
    # 添加填写数据
    for mapping in mappings:
        field_id = mapping.get('field_id')
        value = mapping.get('value')
        if value:
            script_lines.append(f"    '{field_id}': '{value}',")
    
    script_lines.extend([
        "  };",
        "",
        "  // 填写表单",
        "  for (const [fieldId, value] of Object.entries(fillData)) {",
        "    const field = document.querySelector(`[id=\"${fieldId}\"], [name=\"${fieldId}\"]`);",
        "    if (field) {",
        "      field.value = value;",
        "      field.dispatchEvent(new Event('input', { bubbles: true }));",
        "      field.dispatchEvent(new Event('change', { bubbles: true }));",
        "      console.log(`✓ 已填写: ${fieldId}`);",
        "    } else {",
        "      console.warn(`⚠️ 未找到字段: ${fieldId}`);",
        "    }",
        "  }",
        "",
        "  console.log('✓ 表单填写完成！');",
        "})();"
    ])
    
    return "\n".join(script_lines)


@router.get("/status")
async def get_automation_status():
    """获取智能填写模块状态"""
    return {
        "code": 0,
        "message": "智能填写模块运行正常",
        "data": {
            "smart_fill": "available",
            "field_matcher": "available",
            "script_generator": "available"
        }
    }