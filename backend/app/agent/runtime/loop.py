"""
Agent 循环引擎 - 核心运行时

执行流程：
1. 接收用户输入，加入 state
2. 调用 LLM（带工具定义）
3. 若 LLM 返回 tool_calls → 执行工具 → 结果加入 state → 回到第 2 步
4. 若 LLM 返回 content（无 tool_calls）→ 任务完成，返回
5. 全程流式输出事件
"""

import uuid
import logging
from typing import AsyncIterator, Optional

from app.core.llm import LLMProvider, Message
from .base_tool import BaseTool, ToolResult
from .registry import ToolRegistry
from .state import AgentState
from .events import (
    AgentEvent, ContentDelta, ToolCallStart, ToolResultEvent,
    DoneEvent, ConfirmRequiredEvent, ErrorEvent,
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
        from app.core.llm import ToolCall

        tools_schema = self.registry.schemas()
        all_messages = self.state.messages   # 含 system

        for step in range(self.max_steps):
            logger.info(f"Agent step {step + 1}/{self.max_steps}")

            content_acc = ""
            tool_calls: list[ToolCall] = []

            # 流式调用 LLM
            async for chunk in self.llm.chat_stream(
                messages=all_messages,
                tools=tools_schema if tools_schema else None,
                temperature=self.temperature,
            ):
                if chunk["type"] == "content":
                    content_acc += chunk["delta"]
                    yield ContentDelta(delta=chunk["delta"])
                elif chunk["type"] == "tool_call":
                    tool_calls.append(chunk["tool_call"])
                elif chunk["type"] == "done":
                    usage = chunk.get("usage")

            # 把 assistant 消息加入 state
            self.state.add_assistant(
                content=content_acc if content_acc else None,
                tool_calls=tool_calls,
            )

            # 没有 tool_call → 任务完成
            if not tool_calls:
                yield DoneEvent(
                    session_id=self.state.session_id or "",
                    finish_reason="stop",
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
                        self.state.register_pending_action(action_id, {
                            "tool_name": tc.name,
                            "arguments": tc.arguments,
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

                # 把工具结果加入 state
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

        if not approved:
            # 用户拒绝，加入 tool 结果说明
            self.state.add_tool_result(
                tool_call_id=f"rejected_{action_id}",
                name=info["tool_name"],
                content=f"用户拒绝了 {info['tool_name']} 操作",
            )
            yield ToolResultEvent(
                tool_call_id=f"rejected_{action_id}",
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
                    tool_call_id=f"approved_{action_id}",
                    name=info["tool_name"],
                    content=result.to_message_content(),
                )
                yield ToolResultEvent(
                    tool_call_id=f"approved_{action_id}",
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
