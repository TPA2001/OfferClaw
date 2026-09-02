"""
账号 API：注册 / 登录 / 当前用户 / 修改密码 / 找回密码 / 重置密码

无需鉴权即可到达的接口：register / login / forgot-password / reset-password；
其余（me / change-password）依赖 get_current_user。

找回密码说明（无邮件服务的低成本方案）：
- 用户提交注册邮箱 → 服务端生成一次性重置令牌（1 小时有效，仅存哈希）
- 令牌原文写入服务端日志（docker logs 可见），管理员把它交给用户即可完成重置
- 后续接入 SMTP 后可改为邮件投递；AUTH_RESET_TOKEN_IN_RESPONSE=1 时令牌直接随响应返回（仅限内网调试）
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    valid_email,
    valid_username,
    validate_password_strength,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.response import ok, APIError
from app.core.rate_limit import rate_limit
from app.models.user import User

logger = logging.getLogger("offercabin.api.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 重置令牌有效期（小时）
RESET_TOKEN_TTL_HOURS = 1


# ============ 请求模型 ============

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    account: str  # 用户名或邮箱
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ============ 辅助函数 ============

def _user_info(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role or "user",
        "is_admin": (user.role or "user") == "admin",
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _token_payload(user: User) -> dict:
    return {
        "token": create_access_token(user.id, user.token_version),
        "token_type": "bearer",
        "user": _user_info(user),
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============ 接口 ============

@router.post("/register")
async def register(
    req: RegisterRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(5, 60)),
):
    """注册新账号"""
    # 邀请码门控（用于售卖账号：设置 REGISTRATION_INVITE_CODE 后必须凭码注册）
    expected_invite = settings.registration_invite_code
    if expected_invite:
        if not req.invite_code or req.invite_code.strip() != expected_invite:
            raise APIError(40300, "邀请码无效，请联系管理员获取")

    if not valid_username(req.username):
        raise APIError(40000, "用户名需为 2-32 位字母/数字/下划线/中文")
    if not valid_email(req.email):
        raise APIError(40000, "邮箱格式不正确")
    weak_reason = validate_password_strength(req.password)
    if weak_reason:
        raise APIError(40000, weak_reason)

    username = req.username.strip()
    email = req.email.strip().lower()

    exists = (
        db.query(User)
        .filter(or_(User.username == username, User.email == email))
        .first()
    )
    if exists:
        field = "用户名" if exists.username == username else "邮箱"
        raise APIError(40900, f"{field}已被注册")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"新用户注册: {username} ({email})")
    return ok(_token_payload(user), message="注册成功")


@router.post("/login")
async def login(
    req: LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(10, 60)),
):
    """登录（用户名或邮箱 + 密码）"""
    account = req.account.strip()
    user = (
        db.query(User)
        .filter(or_(User.username == account, User.email == account.lower()))
        .first()
    )
    if user is None or not verify_password(req.password, user.password_hash):
        raise APIError(40100, "账号或密码错误")
    if not user.is_active:
        raise APIError(40102, "账号已被停用，请联系管理员")

    return ok(_token_payload(user), message="登录成功")


@router.get("/me")
async def me(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前登录用户信息"""
    user = db.get(User, user_id)
    if user is None:
        raise APIError(40100, "账号不存在")
    return ok(_user_info(user))


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改密码（需登录，校验旧密码；成功后签发新 Token，旧 Token 全部失效）"""
    user = db.get(User, user_id)
    if user is None:
        raise APIError(40100, "账号不存在")
    if not verify_password(req.old_password, user.password_hash):
        raise APIError(40000, "原密码错误")
    weak_reason = validate_password_strength(req.new_password)
    if weak_reason:
        raise APIError(40000, weak_reason)

    user.password_hash = hash_password(req.new_password)
    user.token_version += 1
    db.commit()
    db.refresh(user)

    logger.info(f"用户修改密码: {user.username}")
    return ok(_token_payload(user), message="密码已修改，已自动刷新登录状态")


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(5, 60)),
):
    """发起找回密码：生成一次性重置令牌

    无论邮箱是否存在都返回成功（不泄露注册信息）。
    令牌原文会记录到服务端日志，由管理员转交给用户；
    内网调试可设 AUTH_RESET_TOKEN_IN_RESPONSE=1 让令牌直接返回。
    """
    email = req.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    data: dict = {"delivered": "log"}
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = _hash_token(token)
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=RESET_TOKEN_TTL_HOURS
        )
        db.commit()

        logger.info(
            f"[找回密码] 用户 {user.username} 的重置令牌（{RESET_TOKEN_TTL_HOURS} 小时内有效）: {token}"
        )
        if settings.auth_reset_token_in_response:
            data = {"delivered": "response", "reset_token": token}

    return ok(data, message="如该邮箱已注册，重置令牌已生成，请联系管理员获取")


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """使用重置令牌设置新密码"""
    weak_reason = validate_password_strength(req.new_password)
    if weak_reason:
        raise APIError(40000, weak_reason)

    token_hash = _hash_token(req.token.strip())
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()
    if user is None:
        raise APIError(40000, "重置令牌无效")

    expires_at = user.reset_token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        # SQLite 读取 DateTime(timezone=True) 会丢失 tz 信息，按 UTC 处理
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at < datetime.now(timezone.utc):
        # 顺手清理过期令牌
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        db.commit()
        raise APIError(40000, "重置令牌已过期，请重新发起找回密码")

    user.password_hash = hash_password(req.new_password)
    user.token_version += 1
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.commit()
    db.refresh(user)

    logger.info(f"用户通过重置令牌设置新密码: {user.username}")
    return ok(_token_payload(user), message="密码已重置，请使用新密码登录")
