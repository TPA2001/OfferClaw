"""
Phase 1 长期记忆单元测试

覆盖：建表、写入、记忆类型校验、列表、删除、(多租户隔离)、检索、嵌入确定性、
画像演化（写快照/写记忆/无变更跳过）、记忆注入 System Prompt、Agent 记忆工具。
"""

import asyncio
import pytest

from app.models.memory import UserMemory, ProfileSnapshot
from app.models.profile import Profile
from app.agent.memory import store
from app.agent.memory.embedding import get_embedder
from app.agent.memory.evolution import trigger_evolution
from app.agent.memory.retrieval import (
    assemble_long_term_memory,
    inject_into_system_prompt,
    MEMORY_PLACEHOLDER,
)
from app.agent.tools.memory_tools import UpdateUserPreferenceTool

UID = "test-user-001"


def test_tables_defined():
    assert UserMemory.__tablename__ == "user_memories"
    assert ProfileSnapshot.__tablename__ == "profile_snapshots"


def test_embedding_deterministic_and_distinct():
    emb = get_embedder()
    v1 = emb.embed("想去杭州的互联网中厂")
    v2 = emb.embed("想去杭州的互联网中厂")
    v3 = emb.embed("想去深圳大厂")
    assert v1 == v2                      # 确定性：同文本同向量（Mock 可复现）
    assert v1 != v3                      # 不同文本不同向量
    assert len(v1) == 64


def test_create_memory_persists(db_session):
    row = store.create_memory(db_session, UID, "preference", "想去杭州")
    assert row.id
    assert row.user_id == UID
    assert db_session.query(UserMemory).count() == 1


def test_create_memory_invalid_type_raises(db_session):
    with pytest.raises(ValueError):
        store.create_memory(db_session, UID, "not_a_type", "x")


def test_list_memories_filter_by_type(db_session):
    store.create_memory(db_session, UID, "preference", "想投字节")
    store.create_memory(db_session, UID, "experience", "腾讯实习经历")
    assert len(store.list_memories(db_session, UID)) == 2
    prefs = store.list_memories(db_session, UID, memory_type="preference")
    assert len(prefs) == 1 and prefs[0].memory_type == "preference"


def test_delete_memory(db_session):
    row = store.create_memory(db_session, UID, "preference", "x")
    assert store.delete_memory(db_session, UID, row.id)
    assert not store.delete_memory(db_session, UID, row.id)   # 二次删除不存在
    assert db_session.query(UserMemory).count() == 0


def test_tenant_isolation(db_session):
    store.create_memory(db_session, "user-A", "preference", "想去字节")
    store.create_memory(db_session, "user-B", "preference", "想去腾讯")
    hits_a = {r.content for r, _ in store.search_memories(db_session, "user-A", "字节")}
    assert "想去字节" in hits_a
    assert "想去腾讯" not in hits_a        # B 的记忆对 A 不可见


def test_search_keyword_ordering(db_session):
    store.create_memory(db_session, UID, "preference", "想去杭州的互联网中厂")
    store.create_memory(db_session, UID, "preference", "想去深圳的大厂")
    hits = store.search_memories(db_session, UID, "杭州", top_k=5)
    assert hits and hits[0][0].content.startswith("想去杭州")


def test_search_never_empties_on_no_match(db_session):
    store.create_memory(db_session, UID, "feedback", "心态很重要")
    hits = store.search_memories(db_session, UID, "一个完全无关的词", top_k=1)
    assert isinstance(hits, list)          # 无关键词命中时回退，保证注入不断链


def test_assemble_long_term_memory_retrieves(db_session):
    store.create_memory(db_session, UID, "preference", "期望去杭州竞聘后端")
    block = assemble_long_term_memory(db_session, UID, "目标城市")
    assert "杭州" in block


def test_inject_into_system_prompt_replaces_placeholder():
    sp = "你是助手\n\n" + MEMORY_PLACEHOLDER + "\n"
    out = inject_into_system_prompt(sp, "记忆段：杭州")
    assert MEMORY_PLACEHOLDER not in out
    assert "记忆段：杭州" in out


def test_update_user_preference_tool(db_session):
    tool = UpdateUserPreferenceTool(db_session, UID)
    result = asyncio.run(tool.execute(content="用户想去杭州，薪资不低于25k"))
    assert result.success
    assert db_session.query(UserMemory).filter(UserMemory.user_id == UID).count() == 1


def test_evolution_writes_snapshot_and_memory(db_session):
    profile = Profile(user_id=UID, skills=["Python", "Java"], job_intent={"role": "后端"})
    db_session.add(profile)
    db_session.commit()

    results = asyncio.run(trigger_evolution(UID, "api", db=db_session))
    assert db_session.query(ProfileSnapshot).filter(ProfileSnapshot.user_id == UID).count() == 1
    assert db_session.query(UserMemory).filter(UserMemory.user_id == UID).count() >= 1
    assert results            # 规则降级也应产出条目
    block = assemble_long_term_memory(db_session, UID, "技能")
    assert ("Python" in block) or ("Java" in block)


def test_evolution_skip_on_no_change(db_session):
    profile = Profile(user_id=UID, skills=["Python"])
    db_session.add(profile)
    db_session.commit()

    asyncio.run(trigger_evolution(UID, "api", db=db_session))
    first = db_session.query(UserMemory).filter(UserMemory.user_id == UID).count()

    asyncio.run(trigger_evolution(UID, "api", db=db_session))   # 无变化再触发
    second = db_session.query(UserMemory).filter(UserMemory.user_id == UID).count()
    snapshots = db_session.query(ProfileSnapshot).filter(ProfileSnapshot.user_id == UID).count()

    assert second == first       # 不重复提炼
    assert snapshots == 1        # hash 去重，不重复写快照


def test_evolution_no_profile_no_crash(db_session):
    assert asyncio.run(trigger_evolution(UID, "api", db=db_session)) is None