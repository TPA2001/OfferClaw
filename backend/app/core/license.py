"""离线签名密钥授权模块（默认关闭，免费分发无需激活码）

免费分发 / 内测：授权门控默认不启用（is_gate_enabled() 返回 False），
所有功能直接开放，无需任何激活码。

如需启用授权校验（付费分发场景），设置环境变量 OFFERCLAW_LICENSE_GATE=1：
- 密钥为 JWT（RS256 签名），开发者用私钥签发，App 内嵌公钥验签
- 离线校验：无需联网，本地验签 + 过期 + 机器绑定 + 功能分级
- 用户部署后通过 /api/v1/license/activate 提交密钥，激活态缓存到 data/license.dat

密钥约束：过期时间(exp) + 功能分级(features) + 机器绑定(machine)
威胁模型：私钥仅开发者持有，用户无法伪造密钥；公钥内嵌可被提取但仅用于验签
开发便利：设置环境变量 OFFERCLAW_DEV=1 可绕过授权门控（仅供开发/测试）
"""
import os
import uuid
import hashlib
import platform
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import jwt

logger = logging.getLogger("offerclaw.license")

# ── 功能常量 ────────────────────────────────────────────────────────────
FEATURE_SMART_FILL = "smart_fill"   # 智能填写
FEATURE_AGENT = "agent"             # Agent 助手
FEATURE_DASHBOARD = "dashboard"    # 看板统计
ALL_FEATURES = [FEATURE_SMART_FILL, FEATURE_AGENT, FEATURE_DASHBOARD]

# 路径前缀 → 所需功能 的映射（供中间件门控用）
PATH_FEATURE_MAP = {
    "/api/v1/automation": FEATURE_SMART_FILL,
    "/api/v1/agent": FEATURE_AGENT,
}

# ── 内嵌 RSA-2048 公钥（验签用；私钥仅开发者持有，不分发）────────────────
LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA6RFQEiVpZY4/x4HvEiyp
aVgpIAOJbJ05+/QgoBJhlscqFvkRcGxVtioIQJEy08jjeGo90xNg2X6vgfog95F6
sRV49HaD7TBhHkFLuSafvS2ceDzQxvp59Aq6L+QeWCYZIpOXpeTNXB8KdgZCEvqu
ToeBnwno2W6xLGVqWrIOKsNDAe7rZ6z9yM9ziOqsVnNkOBF8IJef1ABqvnoG4JgX
p15suH7VMRk/Yu1rZxhyCpv81qJPRk4V+rNA8GL7ocAd4g74MYQs9izitbPDffih
pqqoEpVZMSHl0CfL+f6QuhJhcIIw6sf+6cwXkmWevOHMwAOMPOO9N9VGrz2A/aHA
gwIDAQAB
-----END PUBLIC KEY-----"""

PRODUCT_NAME = "offerclaw"

# 激活态缓存文件
from app.core.paths import data_dir as _data_dir
LICENSE_FILE = _data_dir() / "license.dat"


class LicenseError(Exception):
    """授权校验异常"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class LicenseInfo:
    """已校验通过的授权信息"""
    license_id: str
    customer: str
    product: str
    exp: int                          # 过期 unix 时间戳
    features: List[str] = field(default_factory=list)
    machine: str = ""                 # 绑定的机器指纹（空=不绑定）
    issued_at: int = 0
    raw_token: str = ""               # 原始 token（用于重新校验/展示）

    def is_expired(self) -> bool:
        if not self.exp:
            return False
        return datetime.now(timezone.utc).timestamp() > self.exp

    def expiry_dt(self) -> Optional[datetime]:
        if not self.exp:
            return None
        return datetime.fromtimestamp(self.exp, tz=timezone.utc)

    def has_feature(self, feature: str) -> bool:
        if "*" in self.features:
            return True
        return feature in self.features


# ── 机器指纹 ────────────────────────────────────────────────────────────
def get_machine_fingerprint() -> str:
    """生成稳定的机器指纹（MAC + 主机名 + 架构 + 处理器）

    用于机器绑定：签发密钥时嵌入用户机器指纹，激活时比对。
    取 16 位 hex，便于用户上报与核对。
    """
    node = uuid.getnode()  # 48-bit MAC（跨平台稳定）
    raw = f"{node}|{platform.node()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── 校验 ────────────────────────────────────────────────────────────────
def verify_license(token: str, check_machine: bool = True) -> LicenseInfo:
    """验签并校验密钥，返回 LicenseInfo；失败抛 LicenseError

    校验项：签名(RS256) → product → 过期 → 机器绑定
    """
    token = (token or "").strip()
    if not token:
        raise LicenseError("invalid", "密钥为空")

    try:
        payload = jwt.decode(
            token,
            LICENSE_PUBLIC_KEY_PEM,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise LicenseError("expired", "密钥已过期")
    except jwt.InvalidTokenError as e:
        raise LicenseError("invalid", f"密钥无效：{e}")

    if payload.get("product") != PRODUCT_NAME:
        raise LicenseError("invalid", "密钥产品不匹配")

    features = payload.get("features") or []
    if isinstance(features, str):
        features = [features]

    bound_machine = payload.get("machine") or ""
    if check_machine and bound_machine:
        local_fp = get_machine_fingerprint()
        if bound_machine != local_fp:
            raise LicenseError(
                "machine_mismatch",
                f"密钥绑定机器与当前机器不符（当前指纹 {local_fp}）",
            )

    return LicenseInfo(
        license_id=payload.get("sub") or payload.get("license_id") or "",
        customer=payload.get("customer") or "",
        product=payload.get("product") or "",
        exp=int(payload.get("exp") or 0),
        features=list(features),
        machine=bound_machine,
        issued_at=int(payload.get("iat") or 0),
        raw_token=token,
    )


# ── 授权门控开关（默认关闭 = 不搞激活码）────────────────────
def is_gate_enabled() -> bool:
    """授权门控是否启用（默认 False：免费分发，无需激活码）

    只有显式设置 OFFERCLAW_LICENSE_GATE=1 时才启用授权校验。
    """
    return os.getenv("OFFERCLAW_LICENSE_GATE", "").strip() in ("1", "true", "True", "yes")


# ── 激活态缓存 ───────────────────────────────────────────────────────────
def _is_dev_mode() -> bool:
    """开发/测试模式：绕过授权门控。发布构建切勿设置此环境变量。"""
    return os.getenv("OFFERCLAW_DEV", "").strip() in ("1", "true", "True", "yes")


def save_activation(token: str) -> LicenseInfo:
    """校验并持久化激活态（写入 data/license.dat）"""
    info = verify_license(token, check_machine=True)
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(info.raw_token, encoding="utf-8")
    logger.info(f"授权激活成功：{info.customer}，到期 {info.expiry_dt()}")
    return info


def load_activation() -> Optional[LicenseInfo]:
    """从缓存加载并重新校验激活态；无效则返回 None"""
    if not LICENSE_FILE.exists():
        return None
    try:
        token = LICENSE_FILE.read_text(encoding="utf-8").strip()
        return verify_license(token, check_machine=True)
    except LicenseError as e:
        logger.warning(f"缓存授权失效：{e.code} - {e.message}")
        return None
    except Exception as e:
        logger.warning(f"加载授权缓存异常：{e}")
        return None


def clear_activation() -> None:
    """清除激活态缓存（解绑）"""
    try:
        if LICENSE_FILE.exists():
            LICENSE_FILE.unlink()
        logger.info("已清除授权激活缓存")
    except Exception as e:
        logger.warning(f"清除激活缓存异常：{e}")


# ── 全局访问（进程级缓存，避免每次请求读盘）──────────────────────────────
_current_license: Optional[LicenseInfo] = None


def init_license() -> Optional[LicenseInfo]:
    """启动时调用：加载激活态到内存缓存"""
    global _current_license
    if _is_dev_mode():
        logger.warning("[授权] 开发模式(OFFERCLAW_DEV=1)：绕过授权门控，仅供开发测试")
        _current_license = None  # dev 模式下视为开放
        return None
    _current_license = load_activation()
    if _current_license:
        if _current_license.is_expired():
            logger.warning(f"[授权] 密钥已过期（到期 {_current_license.expiry_dt()}）")
        else:
            logger.info(f"[授权] 已激活：{_current_license.customer}，到期 {_current_license.expiry_dt()}")
    else:
        logger.warning("[授权] 未激活：仅 /api/v1/license/* 可用，需提交密钥激活")
    return _current_license


def get_license() -> Optional[LicenseInfo]:
    """获取当前激活态（dev 模式返回 None 表示开放）"""
    return _current_license


def is_activated() -> bool:
    """是否已激活（dev 模式视为已激活）"""
    if _is_dev_mode():
        return True
    info = _current_license
    return info is not None and not info.is_expired()


def is_dev_mode() -> bool:
    """供路由层判断是否开放模式"""
    return _is_dev_mode()


def is_feature_enabled(feature: str) -> bool:
    """某功能是否授权（dev 模式或已激活且含该功能）"""
    if _is_dev_mode():
        return True
    info = _current_license
    if info is None or info.is_expired():
        return False
    return info.has_feature(feature)


def require_feature_for_path(path: str) -> Optional[str]:
    """路径所需功能；返回 None 表示核心功能（仅需有效授权）"""
    for prefix, feat in PATH_FEATURE_MAP.items():
        if path.startswith(prefix):
            return feat
    return None
