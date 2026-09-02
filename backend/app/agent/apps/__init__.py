"""
Agent 应用层 - 对应 Pi 的 pi-coding-agent 包
针对具体场景定义 Agent 的系统提示词、工具组合、行为准则
"""

from .job_agent import (
    create_job_agent,
    JOB_AGENT_PROMPT,
    build_system_prompt,
    build_tool_registry,
)

__all__ = [
    "create_job_agent",
    "JOB_AGENT_PROMPT",
    "build_system_prompt",
    "build_tool_registry",
]
