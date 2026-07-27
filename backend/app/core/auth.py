"""Authentication module

通过环境变量 AUTH_MODE 选择鉴权策略：
- demo (默认)：任意 token 返回 demo-user-123，便于本地开发联调
- jwt：校验 HS256 JWT（用 SECRET_KEY 签名），从 sub claim 取 user_id
- header：从 X-User-ID 请求头读取 user_id（适用于内网网关已鉴权的场景）

Bearer token 可选；未提供时若处于 demo/header 模式会回落到 demo-user-123 / 头部值。
"""
import os
from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

AUTH_MODE = os.getenv("AUTH_MODE", "demo").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-12345")


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
        # 未带 X-User-ID 头时回落到 demo，避免开发环境完全不可用
        return "demo-user-123"

    if mode == "jwt":
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 Bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = _decode_jwt(credentials.credentials)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token 无效或已过期",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id

    # demo 模式（默认）
    return "demo-user-123"


def _decode_jwt(token: str) -> Optional[str]:
    """校验 HS256 JWT 并返回 sub（user_id）；失败返回 None"""
    try:
        import jwt  # PyJWT
    except ImportError:
        # 未安装 PyJWT 时降级：尝试解析不校验签名（仅用于本地调试）
        try:
            import json
            import base64

            payload_b64 = token.split(".")[1]
            # 补齐 base64 padding
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return payload.get("sub")
        except Exception:
            return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        return None
