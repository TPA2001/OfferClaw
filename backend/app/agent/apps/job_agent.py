"""
求职主 Agent
"""

from sqlalchemy.orm import Session

from app.core.llm import LLMProvider
from app.agent.runtime import AgentLoop, AgentState, ToolRegistry
from app.agent.tools import (
    GetProfileTool, UpdateProfileTool,
    CreateApplicationTool, UpdateApplicationStatusTool,
    QueryApplicationsTool, DeleteApplicationTool,
    GetDashboardStatsTool,
    ExtractFormFieldsTool, MatchFieldsTool,
)


JOB_AGENT_PROMPT = """你是 OfferClaw 求职助手，帮助用户管理校招投递全流程。

## 你的能力
- 投递管理：创建/查询/更新/删除投递记录
- 状态追踪：管理投递状态流转（已投递→笔试中→面试中→已录用/已拒绝/已撤回）
- 数据统计：分析投递数据，给出回复率、offer率、平均等待天数等
- 个人画像：查看和更新用户基本信息、教育经历、工作经历、技能、求职意向
- 智能填写：从 URL 抓取网申表单，使用 LLM 进行字段语义匹配

## 行为准则
1. **多步任务先规划**：复杂任务（如"帮我把腾讯的状态更新到面试"）先确认理解正确，再调用工具
2. **信息不足先查询**：不知道用户有哪些投递时，先调用 query_applications 查询，不要凭空回答
3. **敏感操作需确认**：删除记录会触发用户确认流程，告诉用户需要他点击确认
4. **隐私保护**：身份证号、家庭住址等敏感数据由本地浏览器扩展填写，你不接触原文，也不应询问
5. **简洁直接**：调用工具后，用一句话总结结果，不要复述工具返回的 JSON
6. **状态值规范**：调用 update_application_status 时，status 必须是英文枚举值之一：applied/assessment/interview/offer/rejected/withdrawn
7. **不知不编**：不知道的信息如实说不知道，建议用户补充

## 回复风格
- 中文回复
- 简洁、专业、有温度
- 涉及数据时用表格或列表呈现
- 鼓励用户，但不夸大
"""


def create_job_agent(
    llm: LLMProvider,
    db: Session,
    user_id: str,
    session_id: str | None = None,
    max_steps: int = 8,
) -> AgentLoop:
    """创建求职主 Agent 实例"""
    # 注册工具
    registry = ToolRegistry()
    registry.register(GetProfileTool(db, user_id))
    registry.register(UpdateProfileTool(db, user_id))
    registry.register(CreateApplicationTool(db, user_id))
    registry.register(UpdateApplicationStatusTool(db, user_id))
    registry.register(QueryApplicationsTool(db, user_id))
    registry.register(DeleteApplicationTool(db, user_id))
    registry.register(GetDashboardStatsTool(db, user_id))
    registry.register(ExtractFormFieldsTool(db, user_id))
    registry.register(MatchFieldsTool(db, user_id))

    # 初始化状态
    state = AgentState(db=db, user_id=user_id, session_id=session_id)

    return AgentLoop(
        llm=llm,
        registry=registry,
        system_prompt=JOB_AGENT_PROMPT,
        state=state,
        max_steps=max_steps,
    )
