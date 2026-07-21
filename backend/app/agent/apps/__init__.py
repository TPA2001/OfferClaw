"""
Agent 应用层 - 对应 Pi 的 pi-coding-agent 包
针对具体场景定义 Agent 的系统提示词、工具组合、行为准则
"""

from .job_agent import create_job_agent, JOB_AGENT_PROMPT

__all__ = ["create_job_agent", "JOB_AGENT_PROMPT"]
