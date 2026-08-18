"""
Agent 循环引擎 - 核心运行时

执行流程：
1. 接收用户输入，加入 state
2. 调用 LLM（带工具定义）
3. 若 LLM 返回 tool_calls → 执行工具 → 结果加入 state → 回到第 2 步
4. 若 LLM 返回 content（无 tool_calls）→ 任务完成，返回
5. 全程流式输出事件

LLM 流式事件适配：
- LLM 层返回类型化 StreamEvent（TextDelta/ToolCallStart/.../StreamEnd）
- Loop 层转换为 AgentEvent（Pydantic）输出给 API 层
- 推理过程（ReasoningDelta/ReasoningComplete）当前不转发给前端，仅记录日志
"""

import uuid
import logging
from typing import AsyncIterator, Optional

from app.core.llm import LLMProvider, Message, ToolCall
from app.core.llm.events import (
    TextDelta as LLMTextDelta,
    ReasoningDelta, ReasoningComplete,
    ToolCallStart as LLMToolCallStart,
    ToolCallDelta, ToolCallComplete,
    StreamEnd,
)
from .base_tool import BaseTool, ToolResult
from .registry import ToolRegistry
from .state import AgentState
from .events import (
    AgentEvent, ContentDelta, ToolCallStart, ToolResultEvent,
    DoneEvent, ConfirmRequiredEvent, ErrorEvent, NavigateEvent,
)

logger = logging.getLogger("offerclaw.agent.loop")


class AgentLoop:
    """Agent 循环引擎"""

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        system_prompt: str,
        state: AgentState,
        max_steps: int = 10,
        temperature: float = 0.7,
    ):
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.state = state
        self.max_steps = max_steps
        self.temperature = temperature

        # 确保 system prompt 在消息历史开头
        if not self.state.messages or self.state.messages[0].role != "system":
            self.state.messages.insert(0, Message(role="system", content=self.system_prompt))

    async def run_stream(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """流式运行 Agent"""
        self.state.add_user(user_input)

        try:
            async for event in self._loop():
                yield event
        except Exception as e:
            logger.exception(f"Agent 运行异常: {e}")
            yield ErrorEvent(message=str(e))

        # 持久化会话
        self.state.persist()

    async def _loop(self) -> AsyncIterator[AgentEvent]:
        tools_schema = self.registry.schemas()
        all_messages = self.state.messages   # 含 system

        for step in range(self.max_steps):
            logger.info(f"Agent step {step + 1}/{self.max_steps}")

            content_acc = ""
            tool_calls: list[ToolCall] = []
            usage = None
            finish_reason = "stop"

            # 流式调用 LLM（消费类型化 StreamEvent）
            async for event in self.llm.chat_stream(
                messages=all_messages,
                tools=tools_schema if tools_schema else None,
                temperature=self.temperature,
            ):
                if isinstance(event, LLMTextDelta):
                    content_acc += event.text
                    yield ContentDelta(delta=event.text)

                elif isinstance(event, ReasoningDelta):
                    # 推理过程增量，当前不转发给前端
                    logger.debug(f"LLM reasoning: {event.text[:100]}")

                elif isinstance(event, ReasoningComplete):
                    # 推理完成，可记录日志
                    logger.debug(f"LLM reasoning complete: {event.reasoning[:200]}")

                elif isinstance(event, LLMToolCallStart):
                    # 工具调用开始（参数还在 streaming，稍后在 ToolCallComplete 累积）
                    pass

                elif isinstance(event, ToolCallDelta):
                    # 工具参数增量，当前不转发给前端
                    pass

                elif isinstance(event, ToolCallComplete):
                    # 工具调用完成（带完整 arguments）
                    tool_calls.append(ToolCall(
                        id=event.tool_id,
                        name=event.tool_name,
                        arguments=event.arguments,
                    ))

                elif isinstance(event, StreamEnd):
                    # 从 StreamEnd 的 int 字段构造 TokenUsage
                    from app.core.llm import TokenUsage
                    usage = TokenUsage(
                        prompt_tokens=event.input_tokens,
                        completion_tokens=event.output_tokens,
                        total_tokens=event.input_tokens + event.output_tokens,
                        cache_read=event.cache_read,
                        cache_creation=event.cache_creation,
                    )
                    finish_reason = event.finish_reason

            # 把 assistant 消息加入 state
            self.state.add_assistant(
                content=content_acc if content_acc else None,
                tool_calls=tool_calls,
            )

            # 没有 tool_call → 任务完成
            if not tool_calls:
                yield DoneEvent(
                    session_id=self.state.session_id or "",
                    finish_reason=finish_reason,
                    usage=usage,
                )
                return

            # 执行工具调用
            for tc in tool_calls:
                yield ToolCallStart(tool_call=tc)

                tool = self.registry.get(tc.name)
                if not tool:
                    result = ToolResult(
                        success=False,
                        error=f"未知工具: {tc.name}",
                    )
                else:
                    # 需要确认的工具：触发确认事件，挂起等待
                    if tool.requires_confirmation:
                        action_id = f"action_{uuid.uuid4().hex[:12]}"
                        # 保留原始 tool_call_id，确认后用它关联 tool 结果
                        self.state.register_pending_action(action_id, {
                            "tool_name": tc.name,
                            "arguments": tc.arguments,
                            "tool_call_id": tc.id,
                        })
                        yield ConfirmRequiredEvent(
                            action_id=action_id,
                            tool_name=tc.name,
                            description=tool.description,
                            arguments=tc.arguments,
                        )
                        result = ToolResult(
                            success=True,
                            requires_confirmation=True,
                            pending_action_id=action_id,
                            data={"message": f"操作 {tc.name} 等待用户确认 (action_id={action_id})"},
                        )
                    else:
                        result = await tool.arun(**tc.arguments)

                # 把工具结果加入 state（用原始 tool_call_id 关联）
                self.state.add_tool_result(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=result.to_message_content(),
                )

                yield ToolResultEvent(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    success=result.success,
                    data=result.data,
                    error=result.error,
                )

                # navigate_view 工具：额外发出 NavigateEvent 通知前端跳转
                if tc.name == "navigate_view" and result.success and isinstance(result.data, dict):
                    target = result.data.get("target", "")
                    if target:
                        yield NavigateEvent(
                            target=target,
                            params=result.data.get("params", {}) or {},
                            message=result.data.get("message", ""),
                        )

            # 继续下一轮 LLM 调用（带 tool 结果）

        # 超出步数
        yield DoneEvent(
            session_id=self.state.session_id or "",
            finish_reason="max_steps",
        )

    async def resume_after_confirm(self, action_id: str, approved: bool) -> AsyncIterator[AgentEvent]:
        """用户确认操作后恢复执行"""
        info = self.state.resolve_pending_action(action_id)
        if not info:
            yield ErrorEvent(message=f"无效的 action_id: {action_id}")
            return

        # 使用原始 tool_call_id，让模型能正确关联 tool 结果
        original_tool_call_id = info.get("tool_call_id", f"call_{action_id}")

        if not approved:
            # 用户拒绝，加入 tool 结果说明（保留原 tool_call_id）
            self.state.add_tool_result(
                tool_call_id=original_tool_call_id,
                name=info["tool_name"],
                content=f"用户拒绝了 {info['tool_name']} 操作",
            )
            yield ToolResultEvent(
                tool_call_id=original_tool_call_id,
                tool_name=info["tool_name"],
                success=False,
                error="用户拒绝操作",
            )
        else:
            # 用户同意，执行工具
            tool = self.registry.get(info["tool_name"])
            if tool:
                result = await tool.arun(**info["arguments"])
                self.state.add_tool_result(
                    tool_call_id=original_tool_call_id,
                    name=info["tool_name"],
                    content=result.to_message_content(),
                )
                yield ToolResultEvent(
                    tool_call_id=original_tool_call_id,
                    tool_name=info["tool_name"],
                    success=result.success,
                    data=result.data,
                    error=result.error,
                )
            else:
                yield ErrorEvent(message=f"工具 {info['tool_name']} 不存在")

        # 继续 loop
        try:
            async for event in self._loop():
                yield event
        except Exception as e:
            logger.exception(f"Agent 恢复运行异常: {e}")
            yield ErrorEvent(message=str(e))

        self.state.persist()
