"""
画像自动演化服务：检测画像变更 → 后台 LLM 提炼 → 写入长期记忆

触发点：
- api/profile.py 的画像更新（POST /api/v1/profiles/）
- Agent 的 UpdateProfileTool

设计：
- trigger_evolution() 打开独立短会话，fire-and-forget 运行，绝不阻塞主业务流程
- 用规范化 hash 对比最近快照判断是否真的变化，防止重复提炼
- LLM 提炼失败时自动降级为确定性条目（Mock 模式 / 无 Key 均可用）
"""

import hashlib
import json
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.profile import Profile
from app.models.memory import ProfileSnapshot
from app.core.llm import get_default_provider, Message
from app.core.log_utils import get_logger

from . import store
from .embedding import get_embedder
from .schema import EvolutionResult

logger = get_logger("offercabin.agent.memory.evolution")

# 会触发记忆演化的关键字段（姓名等纯身份字段不算记忆）
KEY_FIELDS = ("experience", "skills", "education", "projects", "job_intent")


def _snapshot_data(profile: Profile) -> dict:
    """提取演化的画像关键字段子集"""
    return {
        "experience": profile.experience or [],
        "skills": profile.skills or [],
        "education": profile.education or [],
        "projects": profile.projects or [],
        "job_intent": profile.job_intent or {},
    }


def _canonical(profile_data: dict) -> str:
    """规范化 JSON（稳定排序），用于 hash 比对"""
    return json.dumps(profile_data, ensure_ascii=False, sort_keys=True, default=str)


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _changed_fields(old: dict, new: dict) -> list[str]:
    return [k for k in KEY_FIELDS if json.dumps(old.get(k), default=str, ensure_ascii=False)
            != json.dumps(new.get(k), default=str, ensure_ascii=False)]


async def _digest(fields: list[str], data: dict) -> list[EvolutionResult]:
    """
    LLM 提炼：从变更字段生成结构化记忆条目。
    返回类型稳定的 result（LLM 失败/降级时也返回确定性条目）。
    """
    snapshot_brief = {k: data.get(k) for k in fields}
    prompt = (
        "你是求职助手。用户更新了简历/画像，请基于以下变更提炼 1-3 条长期记忆，"
        "用于 Agent 跨会话引用。只输出 JSON 数组，不要 Markdown：\n"
        f"变更字段：[{', '.join(fields)}]\n"
        f"新值：{json.dumps(snapshot_brief, ensure_ascii=False)}"
    )
    try:
        provider = get_default_provider()
        resp = await provider.chat([Message(role="user", content=prompt)])
        content = (resp.content or "").strip()
        content = content.strip("```json").strip("```").strip()
        parsed = json.loads(content)
        if isinstance(parsed, dict):  # 兼容 {"memories": [...]}
            parsed = parsed.get("memories", [])
        results = []
        for item in parsed if isinstance(parsed, list) else []:
            mt = item.get("memory_type", "preference")
            ct = (item.get("content") or "").strip()
            if mt in ("preference", "experience", "feedback") and ct:
                results.append(EvolutionResult(memory_type=mt, content=ct, related_fields=list(fields)))
        if results:
            return results
    except Exception as e:
        logger.debug(f"LLM 记忆提炼失败，降级为规则条目: {type(e).__name__}")

    return _rule_based_digest(fields, data)


def _rule_based_digest(fields: list[str], data: dict) -> list[EvolutionResult]:
    """规则降级：每个变更字段生成一条确定性记忆（满足 Mock/无 Key 场景）"""
    results: list[EvolutionResult] = []
    for f in fields:
        if f == "job_intent":
            j = data.get("job_intent") or {}
            role = j.get("role")
            cities = j.get("cities") or []
            if role or cities:
                frag = f"求职意向目标：{role or ''}"
                if cities:
                    frag += f"；倾向城市：{'、'.join(cities)}"
                results.append(EvolutionResult(
                    memory_type="preference", content=frag, related_fields=["job_intent"]))
        elif f == "experience":
            exps = data.get("experience") or []
            if exps:
                last = exps[-1]
                frag = f"最新工作经历：{last.get('company','')} — {last.get('title','')}"
                desc = (last.get("description") or "").strip()
                if desc:
                    frag += f"；职责要点：{desc[:80]}"
                results.append(EvolutionResult(
                    memory_type="experience", content=frag, related_fields=["experience"]))
        elif f == "skills":
            skills = data.get("skills") or []
            names = [s.get("name") if isinstance(s, dict) else str(s) for s in skills]
            names = [n for n in names if n]
            if names:
                results.append(EvolutionResult(
                    memory_type="experience", content=f"已掌握技能：{'、'.join(names)}",
                    related_fields=["skills"]))
        elif f == "education":
            edus = data.get("education") or []
            if edus:
                last = edus[-1]
                frag = f"教育背景：{last.get('school','')}{last.get('major','') or ''}（{last.get('degree','')}）"
                results.append(EvolutionResult(
                    memory_type="experience", content=frag, related_fields=["education"]))
        elif f == "projects":
            projs = data.get("projects") or []
            if projs:
                last = projs[-1]
                frag = f"项目经历：{last.get('name','')}（{last.get('role','') or '参与'}）"
                results.append(EvolutionResult(
                    memory_type="experience", content=frag, related_fields=["projects"]))
    return results


async def trigger_evolution(
    user_id: str,
    source: str = "api",
    *,
    db: Optional[Session] = None,
) -> Optional[list[EvolutionResult]]:
    """
    检测画像变更并触发记忆演化。

    - db 为空：自建独立短会话（生产路径，由 BackgroundTasks/create_task 调度）
    - db 传入：复用外部会话（测试注入用）
    内部所有异常兜底，绝不向上抛。
    """
    start = time.monotonic()
    logger.info(f"memory evolution start user_id={user_id}")
    own_session = db is None
    session = db if db is not None else SessionLocal()
    try:
        profile = session.query(Profile).filter(Profile.user_id == user_id).first()
        if not profile:
            logger.debug(f"memory evolution skip: no profile user_id={user_id}")
            return None
        data = _snapshot_data(profile)
        cur_hash = _hash(_canonical(data))

        latest = session.query(ProfileSnapshot).filter(
            ProfileSnapshot.user_id == user_id
        ).order_by(ProfileSnapshot.created_at.desc()).first()

        prev_data = {}
        if latest and latest.profile_hash == cur_hash:
            logger.debug(f"memory evolution skip: no change user_id={user_id}")
            return None
        if latest:
            try:
                prev_data = latest.snapshot or {}
            except Exception:
                prev_data = {}

        fields = _changed_fields(prev_data, data)
        session.add(ProfileSnapshot(
            user_id=user_id,
            profile_hash=cur_hash,
            snapshot=data,
            changed_fields=fields,
            trigger_source=source,
        ))
        session.commit()
        if not fields:
            logger.info(f"memory evolution skip: no key field changed user_id={user_id}")
            return None

        results = await _digest(fields, data)
        embedder = get_embedder()
        inserted = 0
        for r in results:
            vec = embedder.embed(r.content)
            store.create_memory(
                session,
                user_id=user_id,
                memory_type=r.memory_type,
                content=r.content,
                embedding=json.dumps(vec),
                metadata={"related_fields": r.related_fields, "source": source},
                source=source,
            )
            inserted += 1

        duration = round((time.monotonic() - start) * 1000)
        logger.info(
            f"memory evolution done user_id={user_id} source={source} "
            f"fields={','.join(fields) if fields else ''} entries={inserted} duration_ms={duration}"
        )
        return results
    except Exception:
        session.rollback()
        logger.exception(f"memory evolution failed user_id={user_id}")
        return None
    finally:
        duration = round((time.monotonic() - start) * 1000)
        logger.debug(f"memory evolution end user_id={user_id} duration_ms={duration}")
        if own_session:
            session.close()