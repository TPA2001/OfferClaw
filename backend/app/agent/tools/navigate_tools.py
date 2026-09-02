"""
视图导航工具

让 Agent 能主动引导用户跳转到前端功能页面。
这是 OfferCabin 的差异化能力：对话式 Agent 与功能视图无缝衔接。
"""

import logging
from typing import Optional

from ..runtime.base_tool import BaseTool, ToolResult

logger = logging.getLogger("offercabin.agent.tool.navigate")


# 支持的目标路由及其描述
NAVIGATE_TARGETS = {
    "/kanban": {
        "label": "投递看板",
        "description": "查看/管理投递记录、拖拽改状态、看统计",
    },
    "/dashboard": {
        "label": "数据概览",
        "description": "投递漏斗、渠道与趋势统计",
    },
    "/profile": {
        "label": "简历画像",
        "description": "编辑求职画像、教育/工作/项目经历、技能",
    },
    "/interview": {
        "label": "面试复盘",
        "description": "AI 辅助面试复盘分析、周报生成",
    },
    "/settings": {
        "label": "设置",
        "description": "系统设置、LLM 配置、数据统计",
    },
}


class NavigateViewTool(BaseTool):
    """
    引导用户跳转到前端功能页面。

    当 Agent 判断用户需要使用某个功能（如看板、简历编辑、智能填表）时，
    调用此工具让前端自动跳转到对应视图。
    """

    name = "navigate_view"
    description = (
        "引导用户跳转到功能页面。"
        "当用户的意图更适合在专门的功能页面完成时调用（而不是在对话中纯文字交互）。"
        "可选目标：/kanban（投递看板）、/dashboard（数据概览）、/profile（简历画像）、"
        "/interview（面试复盘）、/settings（设置）。"
        "调用后前端会自动跳转到对应页面。"
        "参数：target（目标路由，必需），message（给用户的说明，可选）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": list(NAVIGATE_TARGETS.keys()),
                "description": "目标路由路径",
            },
            "message": {
                "type": "string",
                "description": "给用户的说明（可选，默认自动生成）",
            },
        },
        "required": ["target"],
    }

    def __init__(self):
        pass  # 无依赖

    async def execute(
        self,
        target: str,
        message: Optional[str] = None,
    ) -> ToolResult:
        if target not in NAVIGATE_TARGETS:
            return ToolResult(
                success=False,
                error=f"无效的跳转目标: {target}，可选: {', '.join(NAVIGATE_TARGETS.keys())}",
            )

        info = NAVIGATE_TARGETS[target]
        msg = message or f"正在为你打开「{info['label']}」页面"

        logger.info(f"NavigateViewTool: target={target}, message={msg}")

        return ToolResult(
            success=True,
            data={
                "target": target,
                "label": info["label"],
                "message": msg,
                "params": {},
            },
        )
