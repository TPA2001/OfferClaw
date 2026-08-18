"""
LLM Provider 工厂

支持模型分级：
- get_agent_provider(): Agent 编排用，强模型（function calling 稳定）
- get_gen_provider(): 内容生成用，快模型（简历/评分/面试准备）；未配置则复用 agent provider

配置优先级（高 → 低）：
1. 运行时配置文件（config_store 管理，可通过设置 API 热更新）
2. 环境变量：AGENT_* / GEN_* / OPENAI_*（兼容旧配置）
3. Mock 降级

隐私：
- 日志仅记录 model / base_url，绝不记录 API Key
- 对外暴露的配置查询走 config_store.get_masked_config()（脱敏）
"""

import logging
from typing import Optional

from app.core.config_store import get_provider_config, mask_key, reset_runtime_cache
from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .mock_provider import MockProvider
from .retry_provider import RetriableLLMProvider

logger = logging.getLogger("offerclaw.llm.factory")


def create_provider(
    name: Optional[str] = None,
    with_retry: bool = True,
    **kwargs,
) -> LLMProvider:
    """
    创建 LLM Provider 实例

    Args:
        name: provider 名称 (openai/mock)，未指定时从环境变量读取
        with_retry: 是否包装重试装饰器（默认 True）
        **kwargs: provider 特定参数
    """
    import os
    name = name or os.getenv("LLM_PROVIDER", "openai").lower()

    if name == "openai":
        provider = OpenAIProvider(**kwargs)
    elif name == "mock":
        provider = MockProvider(**kwargs)
    else:
        raise ValueError(f"不支持的 LLM provider: {name}")

    if with_retry:
        import os as _os
        max_retries = int(_os.getenv("LLM_MAX_RETRIES", "3"))
        return RetriableLLMProvider(provider, max_retries=max_retries)
    return provider


def _build_openai(
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    with_retry: bool = True,
) -> Optional[LLMProvider]:
    """根据 api_key/model/base_url 构建 OpenAI 兼容 provider，api_key 为空返回 None"""
    if not api_key:
        return None
    kwargs = {"api_key": api_key}
    if model:
        kwargs["model"] = model
    if base_url:
        kwargs["base_url"] = base_url
    return create_provider("openai", with_retry=with_retry, **kwargs)


def get_agent_provider() -> LLMProvider:
    """
    获取 Agent 编排用 Provider（强模型，function calling 稳定）

    优先级：运行时配置文件 > AGENT_* 环境变量 > OPENAI_* 环境变量 > Mock 降级
    """
    cfg = get_provider_config("agent")

    if cfg["api_key"]:
        provider = _build_openai(
            cfg["api_key"],
            model=cfg["model"] or None,
            base_url=cfg["base_url"] or None,
        )
        if provider:
            # 日志仅记录 model / base_url，绝不记录 api_key
            logger.info(
                f"Agent 编排 Provider: {cfg['model'] or 'default'} "
                f"@ {cfg['base_url'] or 'openai'}"
            )
            return provider

    logger.warning("未配置 Agent LLM 密钥，降级使用 Mock Provider")
    return create_provider("mock", with_retry=False)


def get_gen_provider() -> LLMProvider:
    """
    获取内容生成用 Provider（快模型，用于简历/评分/面试准备等单轮生成）

    优先级：运行时配置文件 > GEN_* 环境变量 > 复用 agent provider（单模型场景）
    """
    cfg = get_provider_config("gen")

    if cfg["api_key"]:
        provider = _build_openai(
            cfg["api_key"],
            model=cfg["model"] or None,
            base_url=cfg["base_url"] or None,
        )
        if provider:
            logger.info(
                f"内容生成 Provider: {cfg['model'] or 'default'} "
                f"@ {cfg['base_url'] or 'openai'}"
            )
            return provider

    # 未配置 GEN_* → 复用 agent provider
    return get_agent_provider()


def get_default_provider() -> LLMProvider:
    """
    获取默认 Provider（兼容旧调用，等同于 get_agent_provider）
    """
    return get_agent_provider()


def reload_llm_config() -> None:
    """重置 LLM 相关运行时缓存，使新配置立即生效。

    供设置 API 在保存配置后调用。
    """
    reset_runtime_cache()
    logger.info("LLM 运行时缓存已重置，新配置将立即生效")


__all__ = [
    "create_provider",
    "get_default_provider",
    "get_agent_provider",
    "get_gen_provider",
    "reload_llm_config",
    "mask_key",
]
