"""
LLM Provider 工厂
"""

import os
import logging
from typing import Optional

from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .mock_provider import MockProvider

logger = logging.getLogger("offerclaw.llm.factory")


def create_provider(
    name: Optional[str] = None,
    **kwargs,
) -> LLMProvider:
    """
    创建 LLM Provider 实例

    Args:
        name: provider 名称 (openai/mock)，未指定时从环境变量读取
        **kwargs: provider 特定参数
    """
    name = name or os.getenv("LLM_PROVIDER", "openai").lower()

    if name == "openai":
        return OpenAIProvider(**kwargs)
    if name == "mock":
        return MockProvider(**kwargs)
    raise ValueError(f"不支持的 LLM provider: {name}")


def get_default_provider() -> LLMProvider:
    """
    获取默认 Provider - 智能降级
    有 OPENAI_API_KEY 用 OpenAI，否则用 Mock
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        logger.info("使用 OpenAI Provider")
        return OpenAIProvider()
    logger.warning("未配置 OPENAI_API_KEY，降级使用 Mock Provider（仅支持关键词触发工具）")
    return MockProvider()
