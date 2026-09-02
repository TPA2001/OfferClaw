"""
工具注册中心
"""

import logging
from typing import Optional

from .base_tool import BaseTool
from app.core.llm import ToolSchema

logger = logging.getLogger("offercabin.agent.registry")


class ToolRegistry:
    """工具注册中心 - 管理 agent 可用的所有工具"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning(f"工具 {tool.name} 已存在，覆盖注册")
        self._tools[tool.name] = tool
        logger.debug(f"注册工具: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[ToolSchema]:
        """所有工具的 schema，用于传给 LLM"""
        return [t.to_schema() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
