"""
Agent 工具层
封装业务能力为 agent 可调用的工具

工具分组：
- profile: 画像管理
- application: 投递记录管理
- dashboard: 看板统计
- followup: 跟进与搜索
- smart_fill: 智能填表（OfferClaw 独有）
- job: 投递前准备（JD分析/简历/求职信/面试准备）
- job_eval: 岗位分析与搜索（OfferClaw 独有：真实性判断 + Boss 搜索）
- feature: Feature 模块工具（公司调研/模拟面试/求职日志）
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
from .feature_tools import (
    ResearchCompanyTool,
    GenerateInterviewQuestionsTool, EvaluateInterviewAnswerTool,
    ReviewInterviewTool, CreateJournalEntryTool, GenerateWeeklySummaryTool,
)
from .navigate_tools import NavigateViewTool

__all__ = [
    # 画像管理
    "GetProfileTool", "UpdateProfileTool",
    # 投递记录管理
    "CreateApplicationTool", "UpdateApplicationTool", "UpdateApplicationStatusTool",
    "QueryApplicationsTool", "DeleteApplicationTool",
    # 看板与统计
    "GetDashboardStatsTool",
    "GetFollowupsTool", "SearchApplicationsTool",
    "GetTimelineStatsTool", "GetCompanyStatsTool",
    # 智能填写（OfferClaw 独有）
    "ExtractFormFieldsTool", "MatchFieldsTool",
    # 投递前准备能力
    "ExtractJobDescriptionTool", "ScoreJobMatchTool",
    "GenerateResumeTool", "GenerateCoverLetterTool",
    "PrepareInterviewTool", "GetApplicationAdviceTool",
    # 岗位分析与搜索能力（OfferClaw 独有）
    "VerifyJobAuthenticityTool", "SearchJobsTool", "EvaluateJobTool",
    # Feature 模块工具（借鉴 CareerDesk）
    "ResearchCompanyTool",
    "GenerateInterviewQuestionsTool", "EvaluateInterviewAnswerTool",
    "ReviewInterviewTool", "CreateJournalEntryTool", "GenerateWeeklySummaryTool",
    # 视图导航（OfferClaw 独有：Agent 与功能视图无缝衔接）
    "NavigateViewTool",
]
