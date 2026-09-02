# -*- coding: utf-8 -*-
"""
Agent 自动化评测脚本

用途：对 Agent 的工具选择准确率等指标进行回归评测，输出 Markdown 报告 + 终端彩色摘要。

设计：
- 黄金数据集：backend/evals/datasets/*.jsonl
- Runner：一个可注入的异步函数 `async def runner(user_input) -> list[str]`，
  返回该输入实际调用的工具名列表（按调用顺序）。
  默认实现用 create_job_agent + MockProvider 跑一次真实 Agent 流；
  测试可通过注入 fake runner 做确定性验证。
- 指标：工具选择准确率（expected ∈ invoked_tools）为核心指标。
- 闸门：整体准确率低于阈值（默认 0.85）则退出码非 0（CI 失败）。

用法：
    python scripts/eval_agent.py                  # 跑全量 + 输出报告
    python scripts/eval_agent.py --baseline       # 跑全量并写入 baseline
    python scripts/eval_agent.py --threshold 0.9  # 自定义阈值
    python scripts/eval_agent.py --category profile_query  # 只看某类别
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# 允许从任意 cwd 运行
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.llm.mock_provider import MockProvider
from app.agent.apps import create_job_agent
from app.core.database import SessionLocal
from app.agent.runtime.events import ToolResultEvent

DATASETS_DIR = BACKEND_DIR / "evals" / "datasets"
REPORTS_DIR = BACKEND_DIR / "evals" / "reports"
BASELINE_FILE = REPORTS_DIR / "baseline.json"

DEFAULT_THRESHOLD = 0.85

# 当前 --category 过滤集（支持类别名或数据集文件名主干）
CATEGORY_FILTER: list[str] = []

# 终端颜色（Windows 可关闭）
import colorama  # noqa: F401
colorama.init()

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN = "\033[96m"; BOLD = "\033[1m"; RESET = "\033[0m"


@dataclass
class CaseResult:
    case_id: str
    category: str
    expected: str
    invoked: list[str]
    success: bool
    latency_ms: int = 0


@dataclass
class CategoryMetrics:
    category: str
    total: int
    correct: int = 0
    results: list[CaseResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


# ============ 数据集加载 ============

def load_dataset(path: Path) -> list[dict]:
    """读取单个 JSONL 数据集（跳过注释行）"""
    cases: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cases.append(json.loads(s))
    return cases


def load_all_datasets() -> dict[str, list[dict]]:
    """按类别聚合所有数据集，并给每条附加 dataset（文件名主干，便于过滤）"""
    grouped: dict[str, list[dict]] = {}
    for f in sorted(DATASETS_DIR.glob("*.jsonl")):
        for case in load_dataset(f):
            case = dict(case)
            case["dataset"] = f.stem
            grouped.setdefault(case["category"], []).append(case)
    return grouped


def _show_category(cat: str, cases: list[dict]) -> bool:
    """判断某类别是否应纳入（按类别名或数据集文件名匹配）"""
    names = {cat, *(c.get("dataset", "") for c in cases)}
    return any(c in names for c in CATEGORY_FILTER)


# ============ 默认 Runner ============

_schema_ready = False


def _ensure_schema() -> None:
    """脚本独立运行（未走 FastAPI 启动）时确保建表，避免 'no such table'"""
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import engine, Base
    # 引入全部模型使其注册到 metadata
    from app.models.profile import Profile            # noqa: F401
    from app.models.application import Application, AgentSession  # noqa: F401
    from app.models.user import User                  # noqa: F401
    from app.models.memory import UserMemory, ProfileSnapshot  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _schema_ready = True


async def default_runner(user_input: str) -> list[str]:
    """真实运行一次 Agent（MockProvider），返回实际调用的工具名列表"""
    _ensure_schema()
    llm = MockProvider()
    db = SessionLocal()
    try:
        agent = create_job_agent(llm=llm, db=db, user_id="eval-user")
        invoked: list[str] = []
        async for event in agent.run_stream(user_input):
            if isinstance(event, ToolResultEvent):
                invoked.append(event.tool_name)
        return invoked
    finally:
        db.close()


# ============ 评测执行 ============

async def run_category(
    category: str,
    cases: list[dict],
    runner: Callable[..., list[str]],
) -> CategoryMetrics:
    metrics = CategoryMetrics(category=category, total=len(cases))
    for case in cases:
        t0 = time.perf_counter()
        try:
            invoked = await runner(case["input"])
        except Exception as e:  # noqa: BLE001
            invoked = [f"<error:{type(e).__name__}>"]
        latency_ms = int((time.perf_counter() - t0) * 1000)
        expected = case["expected"]
        success = expected in invoked
        metrics.correct += int(success)
        metrics.results.append(CaseResult(
            case_id=case["id"], category=category, expected=expected,
            invoked=invoked, success=success, latency_ms=latency_ms,
        ))
    return metrics


async def evaluate_all(
    runner: Optional[Callable[..., list[str]]] = None,
    categories: Optional[list[str]] = None,
) -> list[CategoryMetrics]:
    global CATEGORY_FILTER
    CATEGORY_FILTER = categories or []
    runner = runner or default_runner
    grouped = load_all_datasets()
    metrics_list: list[CategoryMetrics] = []
    for cat, cases in sorted(grouped.items()):
        if CATEGORY_FILTER and not _show_category(cat, cases):
            continue
        metrics_list.append(await run_category(cat, cases, runner))
    return metrics_list


def overall_accuracy(metrics_list: list[CategoryMetrics]) -> float:
    total = sum(m.total for m in metrics_list)
    correct = sum(m.correct for m in metrics_list)
    return correct / total if total else 0.0


# ============ 报告输出 ============

def _simple_summary_row(metrics: CategoryMetrics) -> str:
    bar = "█" * int(metrics.accuracy * 20) + "░" * (20 - int(metrics.accuracy * 20))
    color = GREEN if metrics.accuracy >= DEFAULT_THRESHOLD else RED
    return (f"  {metrics.category:<8}  {bar}  "
            f"{color}{metrics.accuracy * 100:5.1f}%{RESET}"
            f"  ({metrics.correct}/{metrics.total})")


def print_color_summary(metrics_list: list[CategoryMetrics]) -> None:
    """终端彩色摘要"""
    print("\n" + f"{BOLD}===== Agent 评测摘要 ====={RESET}")
    for m in metrics_list:
        print(_simple_summary_row(m))
    acc = overall_accuracy(metrics_list)
    total = sum(m.total for m in metrics_list)
    correct = sum(m.correct for m in metrics_list)
    bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
    line = f"  {'整体':<8}  {bar}  {GREEN if acc >= DEFAULT_THRESHOLD else RED}{acc * 100:5.1f}%{RESET}  ({correct}/{total})"
    print(line)

    if not metrics_list:
        print(f"{YELLOW}  （无数据）{RESET}")
        return

    # baseline 对比
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        base_acc = baseline.get("overall_accuracy", None)
        if base_acc is not None:
            diff = acc - base_acc
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
            color = GREEN if diff >= 0 else RED
            print(f"  baseline: {base_acc * 100:.1f}%  diff: {color}{arrow}{abs(diff) * 100:.1f}%{RESET}")

    # 失败用例明细
    fails = [r for m in metrics_list for r in m.results if not r.success]
    if fails:
        print(f"\n{YELLOW}失败用例（{len(fails)} 个）：{RESET}")
        for r in fails[:20]:
            print(f"  - {RED}[{r.category}]{RESET} {r.case_id}: 期望={r.expected} 实际={r.invoked}")
    print()


def build_markdown_report(metrics_list: list[CategoryMetrics]) -> str:
    """生成 Markdown 报告文本"""
    lines = ["# Agent 自动化评测报告", ""]
    lines.append(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 数据集: {len(metrics_list)} 个类别 / {sum(m.total for m in metrics_list)} 条用例")
    acc = overall_accuracy(metrics_list)
    lines.append(f"- 整体工具准确率: **{acc * 100:.2f}%**")
    threshold = DEFAULT_THRESHOLD
    status = "✅ PASS" if acc >= threshold else "❌ FAIL"
    lines.append(f"- 闸门阈值: {threshold * 100:.0f}%  →  **{status}**")
    lines.append("")

    lines.append("## 按类别")
    lines.append("| 类别 | 用例数 | 正确数 | 准确率 |")
    lines.append("|---|---:|---:|---:|")
    for m in metrics_list:
        lines.append(f"| {m.category} | {m.total} | {m.correct} | {m.accuracy * 100:.1f}% |")
    lines.append("")

    lines.append("## 用例明细")
    lines.append("| ID | 类别 | 期望工具 | 实际工具 | 结果 | 延迟(ms) |")
    lines.append("|---|---|---|---|---|---|")
    for m in metrics_list:
        for r in m.results:
            ok = "✅" if r.success else "❌"
            invoked = ", ".join(r.invoked) if r.invoked else "(无)"
            lines.append(f"| {r.case_id} | {r.category} | `{r.expected}` | {invoked} | {ok} | {r.latency_ms} |")
    lines.append("")
    return "\n".join(lines)


def write_report(metrics_list: list[CategoryMetrics]) -> Path:
    """写报告到 evals/reports/last_eval.md，返回路径"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "last_eval.md"
    path.write_text(build_markdown_report(metrics_list), encoding="utf-8")
    return path


def save_baseline(metrics_list: list[CategoryMetrics]) -> None:
    """保存当前变为 baseline"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps({
        "overall_accuracy": overall_accuracy(metrics_list),
        "by_category": {m.category: m.accuracy for m in metrics_list},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def run_gate_check(metrics_list: list[CategoryMetrics], threshold: float) -> bool:
    """闸门：整体准确率 < 阈值 → False（应判失败）"""
    return overall_accuracy(metrics_list) >= threshold


# ============ CLI ============

def _main() -> int:
    parser = argparse.ArgumentParser(description="Agent 工具准确率评测")
    parser.add_argument("--baseline", action="store_true", help="跑完后把结果写为 baseline")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="整体准确率阈值，默认 0.85")
    parser.add_argument("--category", action="append", help="只评测指定类别（可多次），默认全部")
    args = parser.parse_args()

    metrics_list = asyncio.run(evaluate_all(categories=args.category))
    report_path = write_report(metrics_list)
    print_color_summary(metrics_list)
    print(f"报告: {report_path}")

    if args.baseline and metrics_list:
        save_baseline(metrics_list)
        print(f"baseline 已更新: {BASELINE_FILE}")

    passed = run_gate_check(metrics_list, args.threshold)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(_main())