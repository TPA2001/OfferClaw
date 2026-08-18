"""内测模式鉴权模块

内测阶段采用单用户模式：所有请求视为同一个本地用户，不做鉴权校验。
保留 get_current_user 函数签名是为了不破坏现有 API 路由的依赖注入。

后续如需恢复多用户/卡密激活，可在此处重新引入 token 校验逻辑。
"""
import logging

logger = logging.getLogger("offerclaw.auth")

# 内测模式固定用户 ID（所有数据归属此用户）
LOCAL_USER_ID = "local-user"

# 兼容旧代码的常量（不再生效，仅避免外部引用报错）
AUTH_MODE = "open"


def get_current_user() -> str:
    """返回固定的本地用户 ID（内测模式）

    内测阶段不做鉴权：所有请求视为同一个本地用户，直接放行。
    """
    return LOCAL_USER_ID


def validate_auth_config() -> list[str]:
    """内测模式无需校验鉴权配置，返回空列表。

    保留函数签名以兼容 main.py 启动流程。
    """
    return []
