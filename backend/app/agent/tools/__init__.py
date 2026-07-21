"""
Agent 工具层
封装业务能力为 agent 可调用的工具
"""

from .profile_tools import GetProfileTool, UpdateProfileTool
from .application_tools import (
    CreateApplicationTool, UpdateApplicationStatusTool,
    QueryApplicationsTool, DeleteApplicationTool,
)
from .dashboard_tools import GetDashboardStatsTool
from .smart_fill_tools import ExtractFormFieldsTool, MatchFieldsTool

__all__ = [
    "GetProfileTool", "UpdateProfileTool",
    "CreateApplicationTool", "UpdateApplicationStatusTool",
    "QueryApplicationsTool", "DeleteApplicationTool",
    "GetDashboardStatsTool",
    "ExtractFormFieldsTool", "MatchFieldsTool",
]
