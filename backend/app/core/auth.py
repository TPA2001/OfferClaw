"""Authentication module

通过环境变量 AUTH_MODE 选择鉴权策略：
- jwt（推荐）：校验 HS256 JWT（用 SECRET_KEY 签名），从 sub claim 取 user_id
- header：从 X-User-ID 请求头读取 user_id（适用于内网网关已鉴权的场景）
- demo：任意 token 返回 demo-user-123，仅用于本地开发联调（生产环境禁止使用）

安全说明：
- 启动时调用 validate_auth_config() 检测不安全配置（demo 模式 + 非本地源、默认 SECRET_KEY）
- JWT 校验失败必须直接拒绝，禁止"降级解析"避免伪造 token 攻击
- 未安装 PyJWT 时直接报错，不做不安全的降级
"""
import os
import logging
from typing import Optional

from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.response import UnauthorizedError, InternalServerError

logger = logging.getLogger("offerclaw.auth")

security = HTTPBearer(auto_error=False)

AUTH_MODE = os.getenv("AUTH_MODE", "jwt").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "")
DEFAULT_SECRET_WARNING = "dev-secret-key-12345"


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
) -> str:
    """
    根据 AUTH_MODE 解析当前用户 ID

    Returns:
        str: User ID
    """
    mode = AUTH_MODE

    if mode == "header":
        if x_user_id:
            return x_user_id
        # header 模式下未带头部属于配置错误，明确拒绝而非静默降级
        raise UnauthorizedError("header 模式下必须提供 X-User-ID 请求头")

    if mode == "jwt":
        if not credentials:
            raise UnauthorizedError(
                "缺少 Bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = _decode_jwt(credentials.credentials)
        if not user_id:
            raise UnauthorizedError(
                "token 无效或已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id

    if mode == "demo":
        # demo 模式仅在 DEBUG=True 时允许启用（由 validate_auth_config 守护）
        return "demo-user-123"

    # 未知模式
    raise InternalServerError(f"不支持的 AUTH_MODE: {mode}")


def _decode_jwt(token: str) -> Optional[str]:
    """校验 HS256 JWT 并返回 sub（user_id）；失败返回 None

    安全策略：必须用 PyJWT 校验签名，未安装时直接报错，禁止不安全的降级解析。
    """
    try:
        import jwt  # PyJWT
    except ImportError:
        logger.error("JWT 模式需要安装 PyJWT（pip install PyJWT），禁止降级解析")
        raise InternalServerError("服务端未安装 JWT 依赖")

    if not SECRET_KEY or SECRET_KEY == DEFAULT_SECRET_WARNING:
        logger.error("JWT 模式必须配置非默认的 SECRET_KEY 环境变量")
        raise InternalServerError("服务端未配置安全的 SECRET_KEY")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except Exception as e:
        logger.warning(f"JWT 校验失败: {type(e).__name__}")
        return None


def validate_auth_config() -> list[str]:
    """
    启动时检测不安全的鉴权配置，返回警告列表。

    检测规则：
    1. AUTH_MODE=demo 时，若非本地部署则警告
    2. SECRET_KEY 为空或为默认值时，若用 jwt 模式则拒绝启动
    3. AUTH_MODE=jwt 但未安装 PyJWT 时拒绝启动
    """
    warnings = []

    if AUTH_MODE == "demo":
        warnings.append(
            "AUTH_MODE=demo 仅用于本地开发，所有用户共享 demo-user-123 身份，"
            "生产环境请切换到 jwt 或 header 模式"
        )

    if AUTH_MODE == "jwt":
        if not SECRET_KEY:
            raise RuntimeError(
                "AUTH_MODE=jwt 但 SECRET_KEY 未配置。请在 .env 中设置 SECRET_KEY 环境变量。"
            )
        if SECRET_KEY == DEFAULT_SECRET_WARNING:
            raise RuntimeError(
                f"AUTH_MODE=jwt 但 SECRET_KEY 仍为默认值 '{DEFAULT_SECRET_WARNING}'。"
                "请生成强随机密钥（如 openssl rand -hex 32）并设置 SECRET_KEY 环境变量。"
            )
        try:
            import jwt  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "AUTH_MODE=jwt 但未安装 PyJWT。请运行 pip install PyJWT"
            )

    return warnings
