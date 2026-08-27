"""账号鉴权模块

多用户 JWT 鉴权（网页服务模式）：
- 注册/登录后签发 Bearer Token（HS256，默认 7 天有效）
- 业务 API 通过 Depends(get_current_user) 获取当前用户 ID
- 修改/重置密码会递增 token_version，使旧 Token 立即失效
- AUTH_MODE=open 时退化为单用户本地模式（不校验 Token，兼容本地开发）

密码哈希使用标准库 PBKDF2-SHA256（20 万轮迭代），无第三方依赖。
"""
import hashlib
import hmac
import logging
import re
import secrets
import time

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.response import APIError

logger = logging.getLogger("offerclaw.auth")

# open 模式固定用户 ID（历史本地数据归属此用户）
LOCAL_USER_ID = "local-user"

# PBKDF2 迭代轮数（2026 年推荐下限）
PBKDF2_ITERATIONS = 200_000

# 用户名规则：2-32 位字母/数字/下划线/横线/中文
_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,32}$")
# 邮箱宽松校验
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_username(username: str) -> bool:
    return bool(username) and bool(_USERNAME_RE.match(username))


def valid_email(email: str) -> bool:
    return bool(email) and bool(_EMAIL_RE.match(email))


def valid_password(password: str) -> bool:
    """密码至少 8 位，不允许为空或含空白字符"""
    return bool(password) and len(password) >= 8 and len(password) <= 128 and not re.search(r"\s", password)


# ============ 密码哈希（PBKDF2-SHA256，标准库实现） ============

def hash_password(password: str) -> str:
    """生成密码哈希：pbkdf2_sha256$iterations$salt_hex$digest_hex"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码（常数时间比较）"""
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


# ============ JWT 签发与校验 ============

def create_access_token(user_id: str, token_version: int) -> str:
    """签发访问令牌"""
    now = int(time.time())
    ttl = settings.auth_token_ttl_hours * 3600
    payload = {
        "sub": user_id,
        "ver": token_version,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _auth_error(code: int, message: str) -> APIError:
    return APIError(code, message, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(request: Request, db: Session = Depends(get_db)) -> str:
    """FastAPI 依赖：从 Authorization: Bearer <jwt> 解析当前用户 ID

    - AUTH_MODE=open：本地开发模式，固定返回 LOCAL_USER_ID
    - 其余模式：校验 JWT 签名/有效期/token_version/账号状态
    """
    if settings.auth_mode == "open":
        return LOCAL_USER_ID

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise _auth_error(40100, "未登录或缺少访问令牌")

    token = auth_header[7:].strip()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise _auth_error(40101, "登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise _auth_error(40100, "访问令牌无效")

    user_id = payload.get("sub")
    if not user_id:
        raise _auth_error(40100, "访问令牌无效")

    # 延迟导入避免循环依赖
    from app.models.user import User
    user = db.get(User, user_id)
    if user is None:
        raise _auth_error(40100, "账号不存在")
    if not user.is_active:
        raise _auth_error(40102, "账号已被停用，请联系管理员")
    if user.token_version != payload.get("ver"):
        raise _auth_error(40103, "密码已变更，请重新登录")

    return user.id


def validate_auth_config() -> list[str]:
    """启动时校验鉴权配置，返回警告列表"""
    warnings: list[str] = []
    if settings.auth_mode == "open":
        warnings.append(
            "AUTH_MODE=open：单用户本地模式，所有请求不做鉴权，请勿用于公网部署"
        )
    elif settings.secret_key == "dev-secret-key-12345":
        warnings.append(
            "SECRET_KEY 仍为默认值：公网部署前请通过环境变量设置强随机密钥"
        )
    return warnings


# 兼容旧引用（main.py 启动日志等）
AUTH_MODE = settings.auth_mode
