"""
消息序列化层

借鉴 mewcode 的 serialization.py，把 provider 无关的 Message 转换成各家 API 的请求格式。
这一层属于「适配器」职责，provider 只管调用 API，不关心消息格式转换。

支持的目标格式：
- build_chat_completion_messages: OpenAI Chat Completions API（/chat/completions）
  用于 OpenAI 官方 / 国内代理 / Qwen / DeepSeek / GLM 等兼容服务

- build_tools_for_chat_completion: 工具 schema → Chat Completions 格式
  Responses API 风格 {"type":"function","name":"...","parameters":{...}}
  → Chat Completions 风格 {"type":"function","function":{"name":"...","parameters":{...}}}
"""

import json
from typing import Any

from .base import Message, ToolSchema


def build_chat_completion_messages(
    messages: list[Message],
    system: str = "",
) -> list[dict[str, Any]]:
    """把内部 Message 列表转换为 OpenAI Chat Completions 格式。

    - system 消息：{"role": "system", "content": "..."}（合并到头部）
    - user 消息：{"role": "user", "content": "..."}
    - assistant 文本+工具调用：{"role": "assistant", "content": "...", "tool_calls": [...]}
    - tool 结果：{"role": "tool", "tool_call_id": "...", "content": "..."}

    若提供 system 字符串，会作为第一条 system 消息插入头部。
    """
    result: list[dict[str, Any]] = []

    # system 消息插入头部
    if system:
        result.append({"role": "system", "content": system})

    for m in messages:
        if m.role == "tool":
            # 工具结果消息
            result.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content or "",
            })
        elif m.role == "assistant" and m.tool_calls:
            # assistant 消息带工具调用
            tool_calls = []
            for tc in m.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        if isinstance(tc.arguments, dict)
                        else str(tc.arguments),
                    },
                })
            msg: dict[str, Any] = {
                "role": "assistant",
                "content": m.content,  # 可为 None
                "tool_calls": tool_calls,
            }
            result.append(msg)
        else:
            # 普通 user/assistant/system 消息
            result.append({"role": m.role, "content": m.content or ""})

    return result


def build_tools_for_chat_completion(
    tools: list[ToolSchema],
) -> list[dict[str, Any]]:
    """把 ToolSchema 列表转换为 Chat Completions 格式。

    内部 ToolSchema: {"name": "...", "description": "...", "parameters": {...}}
    Chat Completions: {"type": "function", "function": {"name": "...", ...}}
    """
    converted: list[dict[str, Any]] = []
    for t in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        })
    return converted


def parse_tool_call_arguments(raw: str) -> dict[str, Any]:
    """解析工具调用的 arguments 字符串。

    Chat Completions 流式返回的 arguments 是 JSON 字符串片段，需要累积后解析。
    解析失败时返回 {"_raw": raw} 以保留原始内容供调试。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        # 非 dict 的 JSON 值（如纯字符串/数字），包装成 dict
        return {"_value": parsed}
    except json.JSONDecodeError:
        return {"_raw": raw}
