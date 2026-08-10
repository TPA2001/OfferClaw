"""
LLM Provider 工厂

支持模型分级：
- get_agent_provider(): Agent 编排用，强模型（function calling 稳定）
- get_gen_provider(): 内容生成用，快模型（简历/评分/面试准备）；未配置则复用 agent provider

环境变量：
- AGENT_API_KEY / AGENT_MODEL / AGENT_BASE_URL：编排模型配置
- GEN_API_KEY / GEN_MODEL / GEN_BASE_URL：生成模型配置（可选）
- 兼容旧配置：OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL（当未配置 AGENT_* 时使用）
"""

import os
import logging
from typing import Optional

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
    name = name or os.getenv("LLM_PROVIDER", "openai").lower()

    if name == "openai":
        provider = OpenAIProvider(**kwargs)
    elif name == "mock":
        provider = MockProvider(**kwargs)
    else:
        raise ValueError(f"不支持的 LLM provider: {name}")

    if with_retry:
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
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

    优先级：AGENT_API_KEY > OPENAI_API_KEY > Mock 降级
    """
    # 优先读 AGENT_* 配置
    agent_key = os.getenv("AGENT_API_KEY", "")
    if agent_key:
        provider = _build_openai(
            agent_key,
            model=os.getenv("AGENT_MODEL"),
            base_url=os.getenv("AGENT_BASE_URL"),
        )
        if provider:
            logger.info(
                f"Agent 编排 Provider: {os.getenv('AGENT_MODEL', 'default')} "
                f"@ {os.getenv('AGENT_BASE_URL', 'openai')}"
            )
            return provider

    # 兼容旧配置：OPENAI_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        provider = _build_openai(
            openai_key,
            model=os.getenv("OPENAI_MODEL"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        if provider:
            logger.info(
                f"Agent 编排 Provider (OPENAI_*): {os.getenv('OPENAI_MODEL', 'default')} "
                f"@ {os.getenv('OPENAI_BASE_URL', 'openai')}"
            )
            return provider

    logger.warning("未配置 AGENT_API_KEY 或 OPENAI_API_KEY，降级使用 Mock Provider")
    return create_provider("mock", with_retry=False)


def get_gen_provider() -> LLMProvider:
    """
    获取内容生成用 Provider（快模型，用于简历/评分/面试准备等单轮生成）

    优先级：GEN_API_KEY > 复用 agent provider
    未配置 GEN_* 时复用 agent provider（单模型场景）
    """
    gen_key = os.getenv("GEN_API_KEY", "")
    if gen_key:
        provider = _build_openai(
            gen_key,
            model=os.getenv("GEN_MODEL"),
            base_url=os.getenv("GEN_BASE_URL"),
        )
        if provider:
            logger.info(
                f"内容生成 Provider: {os.getenv('GEN_MODEL', 'default')} "
                f"@ {os.getenv('GEN_BASE_URL', 'openai')}"
            )
            return provider

    # 未配置 GEN_* → 复用 agent provider
    return get_agent_provider()


def get_default_provider() -> LLMProvider:
    """
    获取默认 Provider（兼容旧调用，等同于 get_agent_provider）
    """
    return get_agent_provider()
