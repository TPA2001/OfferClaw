"""授权激活 API

用户本地部署后通过本路由提交密钥完成激活：
- POST /api/v1/license/activate   提交密钥激活
- GET  /api/v1/license/status      查询当前激活态（含功能/到期/机器指纹）
- POST /api/v1/license/deactivate  解绑当前机器
- GET  /api/v1/license/machine      获取本机指纹（供用户上报给开发者签发绑定密钥）
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import license as license_mod
from app.core.response import ok, APIError

logger = logging.getLogger("offerclaw.api.license")

router = APIRouter(prefix="/api/v1/license", tags=["license"])


class ActivateRequest(BaseModel):
    key: str = Field(..., description="开发者签发的授权密钥（JWT）")


def _mask_token(token: str) -> str:
    """脱敏展示原始密钥（仅首尾，避免完整泄露"""
    if not token:
        return ""
    if len(token) <= 20:
        return token[:4] + "***"
    return token[:12] + "..." + token[-8:]


def _to_dict(info: Optional[license_mod.LicenseInfo]) -> dict:
    """将 LicenseInfo 转为前端可用的字典（脱敏 token）"""
    if info is None:
        return {
            "activated": False,
            "dev_mode": license_mod.is_dev_mode(),
            "machine_fingerprint": license_mod.get_machine_fingerprint(),
        }
    return {
        "activated": not info.is_expired(),
        "dev_mode": license_mod.is_dev_mode(),
        "license_id": info.license_id,
        "customer": info.customer,
        "features": info.features,
        "expiry": info.expiry_dt().isoformat() if info.expiry_dt() else None,
        "expired": info.is_expired(),
        "machine_bound": info.machine,
        "machine_fingerprint": license_mod.get_machine_fingerprint(),
        "issued_at": (
            datetime.fromtimestamp(info.issued_at, tz=timezone.utc).isoformat()
            if info.issued_at else None
        ),
        "key_preview": _mask_token(info.raw_token),
    }


@router.post("/activate")
async def activate(req: ActivateRequest):
    """提交密钥激活（离线验签 + 机器绑定校验）"""
    try:
        info = license_mod.save_activation(req.key)
    except license_mod.LicenseError as e:
        # 激活失败：业务码 40300，前端据此提示并保留在激活页
        raise APIError(40300, f"激活失败：{e.message}", detail={"code": e.code})
    # 激活成功后刷新进程级缓存
    license_mod.init_license()
    return ok(_to_dict(info), message=f"激活成功：{info.customer}")


@router.get("/status")
async def status():
    """查询当前激活态（无需鉴权，供激活页/前端探测）"""
    return ok(_to_dict(license_mod.get_license()))


@router.get("/machine")
async def machine():
    """获取本机指纹（用户上报给开发者签发机器绑定密钥）"""
    return ok({"fingerprint": license_mod.get_machine_fingerprint()})


@router.post("/deactivate")
async def deactivate():
    """解绑（清除本机激活缓存，密钥本身不失效）"""
    license_mod.clear_activation()
    # 刷新进程级缓存为未激活
    license_mod.init_license()
    return ok({"deactivated": True}, message="已解绑本机")
