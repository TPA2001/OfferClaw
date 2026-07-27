"""
Agent 工具层
封装业务能力为 agent 可调用的工具
"""

from .profile_tools import GetProfileTool, UpdateProfileTool
from .application_tools import (
    CreateApplicationTool, UpdateApplicationTool, UpdateApplicationStatusTool,
    QueryApplicationsTool, DeleteApplicationTool,
)
from .dashboard_tools import GetDashboardStatsTool
from .followup_tools import (
    GetFollowupsTool, SearchApplicationsTool,
    GetTimelineStatsTool, GetCompanyStatsTool,
)
from .smart_fill_tools import ExtractFormFieldsTool, MatchFieldsTool

__all__ = [
    "GetProfileTool", "UpdateProfileTool",
    "CreateApplicationTool", "UpdateApplicationTool", "UpdateApplicationStatusTool",
    "QueryApplicationsTool", "DeleteApplicationTool",
    "GetDashboardStatsTool",
    "GetFollowupsTool", "SearchApplicationsTool",
    "GetTimelineStatsTool", "GetCompanyStatsTool",
    "ExtractFormFieldsTool", "MatchFieldsTool",
]
