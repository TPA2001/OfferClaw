"""
设置 API

提供 LLM 运行时配置的查询与修改，以及连通性测试。

隐私策略：
- GET 永远返回脱敏配置（api_key_masked），绝不返回明文 API Key
- PUT 接受可选 api_key；为空/缺失表示保持不变，避免误清空
- base_url 校验：仅允许 https 或 localhost http
- 日志不记录 API Key
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.config_store import (
    get_masked_config,
    update_provider_config,
    validate_base_url,
)
from app.core.response import ok, BadRequestError

logger = logging.getLogger("offerclaw.api.settings")

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


# ============ 请求模型 ============

class ProviderConfigUpdate(BaseModel):
    """单个 provider（agent/gen）的配置更新"""
    api_key: Optional[str] = Field(
        default=None,
        description="API Key；为空或缺失表示保持不变",
    )
    model: Optional[str] = Field(
        default=None,
        description="模型名称；传空字符串则清除",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="API Base URL；仅允许 https 或 localhost http",
    )


class LlmConfigUpdate(BaseModel):
    """LLM 配置更新请求"""
    agent: Optional[ProviderConfigUpdate] = None
    gen: Optional[ProviderConfigUpdate] = None


# ============ 端点 ============

@router.get("/llm")
async def get_llm_config(user_id: str = Depends(get_current_user)):
    """获取 LLM 配置（脱敏）"""
    cfg = get_masked_config()
    return ok(data=cfg, message="LLM 配置（脱敏）")


@router.put("/llm")
async def update_llm_config(
    body: LlmConfigUpdate,
    user_id: str = Depends(get_current_user),
):
    """更新 LLM 配置（增量合并，保存后立即生效）

    - api_key 为空/缺失：保持不变
    - model / base_url：传空字符串则清除
    - base_url 校验：仅允许 https 或 localhost http
    """
    try:
        if body.agent is not None:
            agent_updates = body.agent.model_dump(exclude_none=False)
            # api_key 为 None 时从 updates 中剔除（表示保持不变）
            if body.agent.api_key is None:
                agent_updates.pop("api_key", None)
            else:
                # 显式传入（含空字符串）：空字符串视为保持不变
                if not body.agent.api_key:
                    agent_updates.pop("api_key", None)
            update_provider_config("agent", agent_updates)

        if body.gen is not None:
            gen_updates = body.gen.model_dump(exclude_none=False)
            if body.gen.api_key is None:
                gen_updates.pop("api_key", None)
            else:
                if not body.gen.api_key:
                    gen_updates.pop("api_key", None)
            update_provider_config("gen", gen_updates)

        # 重新加载运行时缓存
        from app.core.llm import reload_llm_config
        reload_llm_config()

        cfg = get_masked_config()
        logger.info(f"用户 {user_id} 更新了 LLM 配置")
        return ok(data=cfg, message="LLM 配置已保存并即时生效")
    except ValueError as e:
        # base_url 校验失败等
        raise BadRequestError(str(e))
    except Exception as e:
        logger.error(f"更新 LLM 配置失败: {e}")
        raise BadRequestError(f"保存配置失败: {e}")


@router.post("/llm/test")
async def test_llm_connectivity(user_id: str = Depends(get_current_user)):
    """测试 LLM 连通性：发送一条极短消息，返回响应文本与耗时。

    使用当前生效的 agent provider；若为 Mock 模式则返回标记。
    """
    from app.core.llm import get_agent_provider, Message, LLMError, AuthenticationError

    started = time.time()
    provider = get_agent_provider()
    is_mock = provider.name == "mock"

    try:
        messages = [
            Message(
                role="user",
                content='请回复"连通正常"四个字，不要输出其它内容。',
            ),
        ]
        resp = await provider.chat(messages, temperature=0.0, max_tokens=20)
        elapsed = round(time.time() - started, 2)
        return ok(
            data={
                "ok": True,
                "mock": is_mock,
                "provider": provider.name,
                "response": (resp.content or "").strip(),
                "elapsed_ms": int(elapsed * 1000),
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                } if resp.usage else None,
            },
            message="LLM 连通性测试通过",
        )
    except AuthenticationError as e:
        elapsed = round(time.time() - started, 2)
        return ok(
            data={
                "ok": False,
                "mock": is_mock,
                "provider": provider.name,
                "error": "鉴权失败：API Key 无效或已过期",
                "elapsed_ms": int(elapsed * 1000),
            },
            message="LLM 连通性测试失败：鉴权错误",
        )
    except LLMError as e:
        elapsed = round(time.time() - started, 2)
        # 不向前端暴露内部错误详情（可能含 base_url 片段），仅返回分类信息
        return ok(
            data={
                "ok": False,
                "mock": is_mock,
                "provider": provider.name,
                "error": f"LLM 调用失败（{type(e).__name__}）",
                "elapsed_ms": int(elapsed * 1000),
            },
            message="LLM 连通性测试失败",
        )
    except Exception as e:
        elapsed = round(time.time() - started, 2)
        logger.error(f"LLM 连通性测试异常: {type(e).__name__}: {e}")
        return ok(
            data={
                "ok": False,
                "mock": is_mock,
                "provider": provider.name,
                "error": f"未知错误（{type(e).__name__}）",
                "elapsed_ms": int(elapsed * 1000),
            },
            message="LLM 连通性测试失败：未知错误",
        )
