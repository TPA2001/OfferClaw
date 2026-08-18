"""
LLM 运行时配置存储

将 LLM 配置（API Key / Model / Base URL）持久化到本地 JSON 文件，
支持在运行时通过设置 API 修改而无需重启服务。

隐私与安全策略：
- API Key 仅保存在服务端本地文件（backend/data/llm_config.json，已被 .gitignore 排除）
- 对外返回时始终脱敏（mask_key），永不返回明文
- 不在日志中记录 API Key（factory 仅记录 model / base_url）
- base_url 校验：仅允许 https 或 localhost/http（本地开发）
- 配置文件写入时尝试设置仅属主可读写权限（POSIX）

配置优先级（高 → 低）：
1. 运行时配置文件（本模块管理）
2. 环境变量（AGENT_* / GEN_* / OPENAI_*）
3. Mock 降级

数据结构：
{
    "agent": {"api_key": "...", "model": "...", "base_url": "..."},
    "gen":   {"api_key": "...", "model": "...", "base_url": "..."}
}
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger("offerclaw.config_store")

# 配置文件路径：backend/data/llm_config.json
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CONFIG_PATH = _DATA_DIR / "llm_config.json"


def mask_key(key: Optional[str]) -> str:
    """脱敏 API Key：保留首尾各 4 位，中间用 *** 代替。

    - 空值返回空字符串
    - 过短（<=8）返回 ****（完全不暴露）
    """
    if not key:
        return ""
    k = str(key)
    if len(k) <= 8:
        return "****"
    return k[:4] + "***" + k[-4:]


def validate_base_url(url: Optional[str]) -> Optional[str]:
    """校验 base_url 安全性，返回清洗后的 url 或 None。

    仅允许 https，或 http + localhost（本地开发/代理）。
    不合法时返回 None（由调用方决定是否拒绝）。
    """
    if not url:
        return None
    u = url.strip().rstrip("/")
    if not u:
        return None
    try:
        parsed = urlparse(u)
    except Exception:
        return None
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme == "https":
        return u
    if scheme == "http" and host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return u
    # 不允许其它 scheme（如 file:// / javascript:）
    return None


def load_raw() -> dict:
    """读取原始配置（含明文 key），文件不存在或损坏返回空 dict。"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        logger.warning(f"读取 LLM 配置失败，将忽略: {e}")
        return {}


def _restrict_permissions(path: Path) -> None:
    """尝试限制配置文件权限为仅属主可读写。POSIX chmod 600；Windows 静默跳过。"""
    try:
        if os.name == "posix":
            os.chmod(path, 0o600)
    except Exception:
        # 权限设置失败不阻断写入（data 目录本身已 gitignore）
        pass


def save_raw(config: dict) -> None:
    """整体写入配置（含明文 key）。自动创建目录并限制权限。"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _restrict_permissions(CONFIG_PATH)
    logger.info("LLM 配置已更新并持久化")


def get_provider_config(role: str) -> dict:
    """获取指定 role（agent/gen）的合并配置：运行时文件 > 环境变量。

    返回 dict，可能包含 api_key / model / base_url（均为明文，供 factory 使用）。
    """
    file_cfg = load_raw().get(role, {}) or {}

    # role 对应的环境变量前缀
    env_prefix = role.upper()  # AGENT / GEN
    env_key = os.getenv(f"{env_prefix}_API_KEY", "")
    env_model = os.getenv(f"{env_prefix}_MODEL", "")
    env_base = os.getenv(f"{env_prefix}_BASE_URL", "")

    # 兼容旧 OPENAI_* 配置（仅 agent 角色）
    legacy_key = os.getenv("OPENAI_API_KEY", "") if role == "agent" else ""
    legacy_model = os.getenv("OPENAI_MODEL", "") if role == "agent" else ""
    legacy_base = os.getenv("OPENAI_BASE_URL", "") if role == "agent" else ""

    api_key = file_cfg.get("api_key") or env_key or legacy_key or ""
    model = file_cfg.get("model") or env_model or legacy_model or ""
    base_url = file_cfg.get("base_url") or env_base or legacy_base or ""

    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
    }


def get_masked_config() -> dict:
    """获取脱敏后的完整配置，用于 API 返回给前端。

    返回结构：
    {
        "agent": {"provider": "openai", "model": "...", "base_url": "...",
                  "api_key_masked": "sk-1***ab12", "configured": true},
        "gen":   {...},
        "mock_fallback": false
    }
    """
    file_cfg = load_raw()

    def _build_role(role: str) -> dict:
        merged = get_provider_config(role)
        # provider 类型：有 key 视为 openai 兼容；无 key 则待降级
        provider = "openai" if merged["api_key"] else ("mock" if role == "agent" else "")
        return {
            "provider": provider,
            "model": merged["model"],
            "base_url": merged["base_url"],
            "api_key_masked": mask_key(merged["api_key"]),
            "configured": bool(merged["api_key"]),
        }

    agent = _build_role("agent")
    gen = _build_role("gen")
    return {
        "agent": agent,
        "gen": gen,
        "mock_fallback": not agent["configured"],
    }


def update_provider_config(role: str, updates: dict) -> dict:
    """更新指定 role 的配置（增量合并），返回脱敏后的完整配置。

    Args:
        role: "agent" 或 "gen"
        updates: {"api_key"?: "...", "model"?: "...", "base_url"?: "..."}
                 api_key 为空字符串或缺失时保持不变（避免误清空）

    Returns:
        get_masked_config() 的结果
    """
    if role not in ("agent", "gen"):
        raise ValueError(f"非法 role: {role}")

    full = load_raw()
    role_cfg = full.get(role, {}) or {}

    # api_key：仅在显式提供非空值时更新（空字符串视为"保持不变"）
    new_key = updates.get("api_key")
    if new_key:
        role_cfg["api_key"] = str(new_key).strip()

    # model / base_url：允许清空（传空字符串即清除）
    if "model" in updates:
        role_cfg["model"] = (updates.get("model") or "").strip()
    if "base_url" in updates:
        url = (updates.get("base_url") or "").strip()
        if url:
            validated = validate_base_url(url)
            if not validated:
                raise ValueError(
                    f"base_url 不合法：仅允许 https 或 localhost http，收到 {url}"
                )
            url = validated
        role_cfg["base_url"] = url

    full[role] = role_cfg
    save_raw(full)

    # 配置变更后重置运行时缓存（journal service 等）
    reset_runtime_cache()

    return get_masked_config()


def reset_runtime_cache() -> None:
    """重置依赖 LLM provider 的运行时单例缓存，使新配置立即生效。"""
    # 重置 journal service 单例
    try:
        from app.features.journal import _service  # noqa: F401
        import app.features.journal as _journal_mod
        _journal_mod._service = None
    except Exception:
        pass

    # 其它 feature 单例若有类似缓存，可在此扩展
