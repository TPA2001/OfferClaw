"""
OfferClaw Agent 模块

三层架构（参考 Pi）：
- core/llm: LLM 抽象层（对应 pi-ai）
- agent/runtime: Agent 运行时（对应 pi-agent-core）
- agent/apps: 应用层（对应 pi-coding-agent）
- agent/tools: 工具层
- agent/skills: 技能层（借鉴 CareerDesk，SKILL.md 声明式配置）
"""

from .runtime import (
    AgentLoop, AgentState, ToolRegistry,
    BaseTool, ToolResult,
)
from .apps import create_job_agent, JOB_AGENT_PROMPT, build_system_prompt
from .skills import SkillLoader, Skill, get_skill_loader

__all__ = [
    "AgentLoop", "AgentState", "ToolRegistry",
    "BaseTool", "ToolResult",
    "create_job_agent", "JOB_AGENT_PROMPT", "build_system_prompt",
    "SkillLoader", "Skill", "get_skill_loader",
]
