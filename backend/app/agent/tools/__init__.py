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
from .job_tools import (
    ExtractJobDescriptionTool, ScoreJobMatchTool,
    GenerateResumeTool, GenerateCoverLetterTool,
    PrepareInterviewTool, GetApplicationAdviceTool,
)
from .job_eval_tools import (
    VerifyJobAuthenticityTool, SearchJobsTool, EvaluateJobTool,
)

__all__ = [
    "GetProfileTool", "UpdateProfileTool",
    "CreateApplicationTool", "UpdateApplicationTool", "UpdateApplicationStatusTool",
    "QueryApplicationsTool", "DeleteApplicationTool",
    "GetDashboardStatsTool",
    "GetFollowupsTool", "SearchApplicationsTool",
    "GetTimelineStatsTool", "GetCompanyStatsTool",
    "ExtractFormFieldsTool", "MatchFieldsTool",
    # 投递前准备能力（吸取 ai-job-search 优势）
    "ExtractJobDescriptionTool", "ScoreJobMatchTool",
    "GenerateResumeTool", "GenerateCoverLetterTool",
    "PrepareInterviewTool", "GetApplicationAdviceTool",
    # 岗位分析与搜索能力
    "VerifyJobAuthenticityTool", "SearchJobsTool", "EvaluateJobTool",
]
