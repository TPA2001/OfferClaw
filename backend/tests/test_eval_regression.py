# -*- coding: utf-8 -*-
"""
Agent 评测回归测试

验证点：
1. 黄金数据集可解析、数量达标、期望工具名均为 Agent 实际注册工具。
2. 评测闸门逻辑：整体工具准确率 < 85% 时判失败（run_gate_check 返回 False）。
3. Markdown 报告可生成、含关键指标与失败用例。

用注入 fake runner 做确定性验证，不依赖真实 LLM / Mock 判定。
"""

import sys
from pathlib import Path

import pytest

# 使 scripts/eval_agent.py 可导入
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import eval_agent as ev  # noqa: E402


@pytest.fixture
def grouped_datasets():
    return ev.load_all_datasets()


def _registered_tool_names():
    """从 Agent 注册表派生真实工具名集合（与运行时一致）"""
    from app.core.llm.mock_provider import MockProvider
    from app.agent.apps import create_job_agent
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        agent = create_job_agent(MockProvider(), db, "eval-user")
        return {s.name for s in agent.registry.schemas()}
    finally:
        db.close()


def test_datasets_parse_and_counts(grouped_datasets):
    assert set(grouped_datasets.keys()) == {"岗位推荐", "面试复盘", "画像查询"}
    assert len(grouped_datasets["岗位推荐"]) == 20
    assert len(grouped_datasets["面试复盘"]) == 15
    assert len(grouped_datasets["画像查询"]) == 15
    total = sum(len(v) for v in grouped_datasets.values())
    assert total == 50


def test_expected_tools_are_registered(grouped_datasets):
    """数据集里的 expected 工具名必须真实存在，避免跑出无法实现的用例"""
    registered = _registered_tool_names()
    errs = []
    for cases in grouped_datasets.values():
        for c in cases:
            if c["expected"] not in registered:
                errs.append(f"{c['id']}: expected={c['expected']}")
    assert not errs, "存在未注册的期望工具: " + "; ".join(errs)


def test_gate_passes_when_accuracy_high(grouped_datasets):
    """fake runner 全部命中 → 准确率=100% → 闸门通过"""
    mapping = {c["input"]: c["expected"] for cases in grouped_datasets.values() for c in cases}

    async def correct_runner(user_input):
        return [mapping[user_input]]

    metrics = pytest_asyncio_run(ev.evaluate_all(runner=correct_runner))
    assert ev.overall_accuracy(metrics) == 1.0
    assert ev.run_gate_check(metrics, 0.85) is True


def test_gate_fails_below_threshold(grouped_datasets):
    """fake runner 全部选错 → 准确率=0% → 闸门失败（<85%）"""
    mapping = {c["input"]: c["expected"] for cases in grouped_datasets.values() for c in cases}

    async def wrong_runner(user_input):
        return [mapping[user_input] + "_wrong"]

    metrics = pytest_asyncio_run(ev.evaluate_all(runner=wrong_runner))
    assert ev.overall_accuracy(metrics) == 0.0
    assert ev.run_gate_check(metrics, 0.85) is False


def test_markdown_report_contains_key_sections(grouped_datasets):
    """报告包含整体准确率、类别表、失败用例明细"""
    mapping = {c["input"]: c["expected"] for cases in grouped_datasets.values() for c in cases}

    async def half_wrong_runner(user_input):
        # 奇数 id 选对，偶数选错 → 稳定的混合结果
        matched = mapping[user_input]
        if matched.startswith(("evaluate", "get_", "review_")):
            return [matched]
        return [matched + "_x"]

    metrics = pytest_asyncio_run(ev.evaluate_all(runner=half_wrong_runner))
    md = ev.build_markdown_report(metrics)
    assert "Agent 自动化评测报告" in md
    assert "整体工具准确率" in md
    assert "| 类别 | 用例数 | 正确数 | 准确率 |" in md  # 类别表头
    assert "❌" in md      # 存在失败用例
    assert "✅" in md      # 存在通过用例


def pytest_asyncio_run(coro):
    """同步运行 async 协程（不引入 pytest-asyncio 依赖）"""
    import asyncio
    return asyncio.run(coro)