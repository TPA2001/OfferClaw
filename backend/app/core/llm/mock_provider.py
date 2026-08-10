"""
Mock Provider - 无 API Key 时的降级方案
基于规则的伪智能回复，让 Agent 框架可以独立于 LLM 调试
"""

import re
import logging
import uuid
from typing import Optional

from .base import (
    LLMProvider, Message, ToolSchema, ToolCall,
    LLMResponse, TokenUsage,
)

logger = logging.getLogger("offerclaw.llm.mock")


class MockProvider(LLMProvider):
    """Mock Provider - 基于关键词的工具调用模拟"""

    name = "mock"

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolSchema]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        # 如果最后一条是 tool result，说明工具已执行完，直接生成总结回复
        if messages and messages[-1].role == "tool":
            return LLMResponse(
                content=self._summarize_after_tool(messages[-1]),
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
            )

        # 取最后一条 user 消息
        last_user = None
        for m in reversed(messages):
            if m.role == "user":
                last_user = m.content or ""
                break

        if not last_user:
            return LLMResponse(content="有什么可以帮你的？", finish_reason="stop")

        tool_call = self._detect_tool_call(last_user, tools or [])
        if tool_call:
            return LLMResponse(
                content=f"好的，我来帮你执行：{tool_call.name}",
                tool_calls=[tool_call],
                finish_reason="tool_calls",
            )

        # 默认回复
        return LLMResponse(
            content=self._default_reply(last_user),
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    def _summarize_after_tool(self, tool_msg: Message) -> str:
        """工具执行后的总结回复"""
        content = tool_msg.content or ""
        name = tool_msg.name or "工具"

        # 尝试解析 JSON 内容
        import json
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if data.get("error") and not data.get("message"):
                    return f"操作失败：{data['error']}"
                if name == "search_jobs":
                    jobs = data.get("jobs", [])
                    total = data.get("total", len(jobs))
                    source = data.get("source", "unknown")
                    need_login = data.get("need_login", False)
                    keyword = data.get("keyword", "")
                    city = data.get("city", "全国")

                    if need_login:
                        return data.get("message", f"Boss 直聘需要登录后才能搜索「{keyword}」。请先在「智能填写」页面点击「登录 Boss」按钮完成登录。")

                    source_label = {"real": "真实数据", "html": "公开页", "mock": "模拟数据"}.get(source, source)
                    if not jobs:
                        return f"搜索「{keyword}」{city or '全国'}：未找到岗位（数据来源：{source_label}）。"

                    lines = [f"搜索「{keyword}」{city or '全国'}：找到 {total} 个岗位（数据来源：{source_label}）\n"]
                    for i, j in enumerate(jobs[:8], 1):
                        title = j.get("title", "?")
                        company = j.get("company", "?")
                        salary = j.get("salary", "")
                        job_city = j.get("city", "")
                        line = f"{i}. **{company}** - {title}"
                        if salary:
                            line += f" | {salary}"
                        if job_city:
                            line += f" | {job_city}"
                        lines.append(line)
                    if total > 8:
                        lines.append(f"\n...共 {total} 个岗位，如需查看更多请翻页。")
                    return "\n".join(lines)

                if name == "verify_job_authenticity":
                    return data.get("message", "真实性评估完成。")

                if name == "evaluate_job":
                    return data.get("message", "岗位综合评估完成。")

                if data.get("message"):
                    return data["message"]
                if data.get("error"):
                    return f"操作失败：{data['error']}"
                if name == "query_applications":
                    apps = data.get("applications", [])
                    if not apps:
                        return "你还没有任何投递记录。"
                    lines = [f"你目前共有 {data.get('count', len(apps))} 条投递记录："]
                    for i, a in enumerate(apps[:10], 1):
                        lines.append(f"{i}. {a.get('company', '?')} - {a.get('position', '?')}（{a.get('status_label', a.get('status', '?'))}）")
                    if len(apps) > 10:
                        lines.append(f"...共 {len(apps)} 条")
                    return "\n".join(lines)
                if name == "get_dashboard_stats":
                    total = data.get("total", 0)
                    if total == 0:
                        return "你还没有任何投递记录。"
                    by_status = data.get("by_status", {})
                    status_lines = "、".join(f"{k}{v}" for k, v in by_status.items())
                    return (
                        f"你的投递概览：\n"
                        f"- 总投递：{total}\n"
                        f"- 状态分布：{status_lines}\n"
                        f"- 回复率：{data.get('reply_rate', '?')}\n"
                        f"- Offer率：{data.get('offer_rate', '?')}\n"
                        f"- 平均等待：{data.get('avg_wait_days', 0)} 天"
                    )
                if name == "get_profile":
                    if not data.get("profile"):
                        return "你还没有创建画像，可以先告诉我你的基本信息。"
                    return "已获取你的画像信息。"
        except (json.JSONDecodeError, AttributeError):
            pass

        return f"操作完成。"

    def _detect_tool_call(self, text: str, tools: list[ToolSchema]) -> Optional[ToolCall]:
        """基于关键词识别用户意图，触发对应工具"""
        text_lower = text.lower()

        # 岗位搜索（优先匹配，避免被"查看"等关键词截胡）
        # 匹配模式：搜XX岗位 / 搜索XX / 找XX工作 / 找找XX的岗位
        if any(kw in text for kw in ["搜索", "搜一下", "搜下", "找找", "找工作", "找岗位", "有哪些岗位", "帮我搜"]):
            if self._has_tool(tools, "search_jobs"):
                # 尝试提取关键词和城市
                keyword = ""
                city = None

                # 提取城市
                city_patterns = [
                    r"(北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|苏州|天津|重庆|长沙|青岛|大连|厦门|全国)",
                ]
                for cp in city_patterns:
                    cm = re.search(cp, text)
                    if cm:
                        city = cm.group(1)
                        break

                # 提取搜索关键词：去掉"搜/搜索/找/岗位/工作/北京等城市名"后的剩余内容
                kw_text = re.sub(r"(帮我|请|帮忙)?\s*(搜一下|搜下|搜索|找找|找|找工作|找岗位|有哪些岗位|帮我搜)", "", text)
                kw_text = re.sub(r"(北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|苏州|天津|重庆|长沙|青岛|大连|厦门|全国)", "", kw_text)
                kw_text = re.sub(r"(的|地)?\s*(岗位|工作|职位|job)", "", kw_text, flags=re.IGNORECASE)
                kw_text = kw_text.strip(" ，。、？?")

                if kw_text and len(kw_text) >= 1:
                    keyword = kw_text
                else:
                    keyword = "Java"  # 默认兜底

                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="search_jobs",
                    arguments={"keyword": keyword, **({"city": city} if city else {})},
                )

        # 岗位真实性判断
        if any(kw in text for kw in ["靠谱吗", "是不是中介", "真假", "可信", "骗", "皮包", "培训贷", "这个公司怎么样"]):
            if self._has_tool(tools, "verify_job_authenticity"):
                # 尝试提取 URL
                url_match = re.search(r'(https?://[^\s，。]+)', text)
                args = {}
                if url_match:
                    args["jd_url"] = url_match.group(1)
                else:
                    # 无 URL 时把文本作为 jd_text
                    args["jd_text"] = text
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="verify_job_authenticity",
                    arguments=args,
                )

        # 岗位综合评估
        if any(kw in text for kw in ["评估", "综合分析", "值不值得投", "怎么样", "能投吗", "可以投吗", "分析一下"]):
            if self._has_tool(tools, "evaluate_job"):
                url_match = re.search(r'(https?://[^\s，。]+)', text)
                args = {}
                if url_match:
                    args["jd_url"] = url_match.group(1)
                else:
                    args["jd_text"] = text
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="evaluate_job",
                    arguments=args,
                )

        # 查询投递记录
        if any(kw in text for kw in ["查询", "查看", "列出", "有哪些投递", "投递记录", "看板"]):
            if self._has_tool(tools, "query_applications"):
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="query_applications",
                    arguments={},
                )

        # 创建投递
        # 匹配模式：投递了XX公司的XX岗位 / 投了XX的XX / 记录投递XX XX
        create_patterns = [
            r"投递了\s*([^\s,，的]+?)(?:公司)?\s*的\s*([^\s,，]+?)(?:岗位|职位)?(?:。|$)",
            r"投了\s*([^\s,，的]+?)\s*的\s*([^\s,，]+?)(?:岗位|职位)?(?:。|$)",
            r"记录.*?投递.*?([^\s,，]+?)\s+([^\s,，]+?)(?:岗位|职位)?(?:。|$)",
        ]
        for pat in create_patterns:
            m = re.search(pat, text)
            if m and self._has_tool(tools, "create_application"):
                company = m.group(1).strip()
                position = m.group(2).strip()
                # 过滤掉过短或无效的匹配
                if len(company) >= 2 and len(position) >= 2:
                    return ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name="create_application",
                        arguments={
                            "company": company,
                            "position": position,
                        },
                    )

        # 更新状态
        status_map = {
            "笔试": "assessment", "笔试中": "assessment",
            "面试": "interview", "面试中": "interview",
            "offer": "offer", "录用": "offer", "已录用": "offer",
            "拒绝": "rejected", "已拒绝": "rejected",
            "撤回": "withdrawn", "放弃": "withdrawn",
        }
        for kw, status_val in status_map.items():
            if kw in text and self._has_tool(tools, "update_application_status"):
                # 尝试从文本提取 company
                company_match = re.search(r"([^\s,，]{2,20})\s*(?:的)?\s*(?:状态|进度)", text)
                company = company_match.group(1) if company_match else None
                args = {"status": status_val}
                if company:
                    args["company"] = company
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="update_application_status",
                    arguments=args,
                )

        # 查看画像
        if any(kw in text for kw in ["我的画像", "我的信息", "个人资料", "查看画像"]):
            if self._has_tool(tools, "get_profile"):
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="get_profile",
                    arguments={},
                )

        # 看板统计
        if any(kw in text for kw in ["统计", "数据", "看板", "回复率", "offer率", "概览"]):
            if self._has_tool(tools, "get_dashboard_stats"):
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="get_dashboard_stats",
                    arguments={},
                )

        return None

    def _has_tool(self, tools: list[ToolSchema], name: str) -> bool:
        return any(t.name == name for t in tools)

    def _default_reply(self, user_text: str) -> str:
        return (
            "我是 OfferClaw 求职助手，可以帮你：\n"
            "- 🔍 **搜索岗位**（如：'帮我搜北京Java岗位'）\n"
            "- 🛡️ **判断岗位真实性**（如：'这个岗位靠谱吗'）\n"
            "- 📊 **综合评估岗位**（如：'帮我评估这个岗位'）\n"
            "- 📝 **管理投递记录**（如：'记录我投递了腾讯的后端岗位'）\n"
            "- 📋 **查询投递状态**（如：'查看我的投递记录'）\n"
            "- 🔄 **更新状态**（如：'腾讯进入面试'）\n"
            "- 📈 **查看统计**（如：'我的投递统计'）\n"
            "- 👤 **维护个人画像**\n\n"
            "请告诉我你想做什么？"
        )
