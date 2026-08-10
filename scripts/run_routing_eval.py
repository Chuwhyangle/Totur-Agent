"""FR-5: 路由准确率评测（不执行工具，只读模型选择的工具名）。

只发一次带 tools schema 的 LLM 调用，读 tool_calls[*].function.name。
不跑完整 ReAct、不执行工具——快、便宜、可复现。

输出：整体路由准确率 + 分 group 准确率 + 混淆矩阵。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.llm_client import create_llm_client
from app.config import load_llm_config
from app.services.agent.tools.registry import ToolRegistry
from app.services.retrieval_eval import RetrievalEvalCase, load_eval_cases


DEFAULT_EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "joint_plus_jd_eval.jsonl"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "routing_eval"


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Evaluate RAG routing accuracy.")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument(
        "--case-ids",
        default="",
        help="Comma-separated case ids to run, for example rag_pos_001,jd_pos_002.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Run only the first N selected cases."
    )
    parser.add_argument(
        "--allow-full",
        action="store_true",
        help="Allow running the full eval set. Use sparingly.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Pause between LLM calls to reduce provider pressure.",
    )
    parser.add_argument("--jsonl-output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        case_ids = _parse_csv(args.case_ids)
        _validate_run_scope(case_ids, args.limit, args.allow_full)

        all_cases = load_eval_cases(args.eval_file)
        cases = _select_cases(all_cases, case_ids=case_ids, limit=args.limit)
        if not cases:
            raise RuntimeError("no routing eval cases selected.")

        config = load_llm_config()
        client = create_llm_client(config)
        registry = ToolRegistry()
        tools = registry.get_tools_schema()

        records: list[dict] = []
        for index, case in enumerate(cases, start=1):
            print(
                "running {index}/{total}: {case_id} group={group}".format(
                    index=index,
                    total=len(cases),
                    case_id=case.case_id,
                    group=case.group,
                )
            )
            chosen = _ask_model_tool_choice(
                client=client,
                model=config.model,
                tools=tools,
                query=case.query,
            )
            records.append(
                {
                    "case_id": case.case_id,
                    "group": case.group,
                    "query": case.query,
                    "expected_tool": case.expected_tool,
                    "expected_tools": list(case.expected_tools),
                    "chosen_tools": sorted(chosen),
                    "correct": _is_correct(case, chosen),
                }
            )
            if args.delay_seconds > 0:
                import time

                time.sleep(args.delay_seconds)

        summary = _summarize(records)
        jsonl_output, markdown_output = _resolve_outputs(
            args.jsonl_output,
            args.markdown_output,
        )
        _write_jsonl(jsonl_output, records)
        markdown_output.write_text(
            _format_markdown(summary, records),
            encoding="utf-8",
        )
        print(_format_console(summary))
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"路由评测失败：{exc}", file=sys.stderr)
        return 1

    print(f"jsonl={jsonl_output}")
    print(f"markdown={markdown_output}")
    return 0


def _ask_model_tool_choice(*, client, model: str, tools: list[dict], query: str) -> set[str]:
    """一次带 tools 的模型调用，返回模型选择的工具名集合。"""

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个路由决策器。根据用户问题，决定是否需要调用本地工具，"
                    "以及调用哪个工具。只需要返回工具调用，不要输出文字。"
                ),
            },
            {"role": "user", "content": query},
        ],
        tools=tools,
        tool_choice="auto",
    )
    message = completion.choices[0].message
    chosen: set[str] = set()
    for tool_call in (message.tool_calls or []):
        name = getattr(tool_call, "function", None)
        if name is not None and getattr(name, "name", None):
            chosen.add(name.name)
    return chosen


def _is_correct(case: RetrievalEvalCase, chosen: set[str]) -> bool:
    """单工具用例：chosen == {expected_tool}；跨域用例：chosen == expected_tools；负例：chosen 为空。"""

    expected = case.expected_tool_set
    if not expected:
        # negative_out_of_scope：期望不调用任何工具
        return not chosen
    if case.expected_tool and len(case.expected_tool_set) == 1:
        # 单工具：必须恰好调用该工具，且不调用其他工具
        return chosen == expected
    # 跨域：调用的工具集合必须等于期望集合（顺序无关）
    return chosen == expected


def _select_cases(
    cases: list[RetrievalEvalCase],
    *,
    case_ids: list[str],
    limit: int | None,
) -> list[RetrievalEvalCase]:
    if case_ids:
        by_id = {case.case_id: case for case in cases}
        missing = [case_id for case_id in case_ids if case_id not in by_id]
        if missing:
            raise ValueError(f"unknown eval case ids: {missing}")
        selected = [by_id[case_id] for case_id in case_ids]
    else:
        selected = list(cases)

    if limit is not None:
        selected = selected[:limit]
    return selected


def _summarize(records: list[dict]) -> dict:
    """计算整体/分 group 准确率 + 混淆矩阵。"""

    total = len(records)
    correct = sum(1 for record in records if record["correct"])
    overall = round(correct / total, 4) if total else 0.0

    by_group: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_group[record["group"]].append(record)

    group_metrics: dict[str, dict] = {}
    confusion: Counter = Counter()
    group_confusion: dict[str, Counter] = defaultdict(Counter)
    for group, group_records in by_group.items():
        group_total = len(group_records)
        group_correct = sum(1 for record in group_records if record["correct"])
        group_metrics[group] = {
            "total": group_total,
            "correct": group_correct,
            "accuracy": round(group_correct / group_total, 4) if group_total else 0.0,
            "misclassified": [
                {
                    "case_id": record["case_id"],
                    "query": record["query"],
                    "expected": record["expected_tool"]
                    or record["expected_tools"]
                    or "none",
                    "chosen": record["chosen_tools"] or "none",
                }
                for record in group_records
                if not record["correct"]
            ],
        }
        for record in group_records:
            expected = record["expected_tool"] or (record["expected_tools"][0] if record["expected_tools"] else "none")
            chosen = record["chosen_tools"][0] if record["chosen_tools"] else "none"
            confusion[(expected, chosen)] += 1
            group_confusion[group][(expected, chosen)] += 1

    return {
        "total": total,
        "correct": correct,
        "overall_accuracy": overall,
        "group_metrics": group_metrics,
        "confusion_matrix": [{"expected": e, "chosen": c, "count": n} for (e, c), n in confusion.most_common()],
        "group_confusion": {
            group: [{"expected": e, "chosen": c, "count": n} for (e, c), n in counter.most_common()]
            for group, counter in group_confusion.items()
        },
    }


def _format_console(summary: dict) -> str:
    lines = [f"routing_eval: total={summary['total']} correct={summary['correct']} accuracy={summary['overall_accuracy']}"]
    for group, metrics in sorted(summary["group_metrics"].items()):
        lines.append(
            f"  {group}: {metrics['correct']}/{metrics['total']} accuracy={metrics['accuracy']}"
        )
    return "\n".join(lines)


def _format_markdown(summary: dict, records: list[dict]) -> str:
    lines = [
        "# Routing Eval Report",
        f"- 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 总用例：{summary['total']}",
        f"- 正确：{summary['correct']}",
        f"- 整体准确率：**{summary['overall_accuracy']}**",
        "",
        "## 分 group 准确率",
        "| group | total | correct | accuracy |",
        "|---|---|---|---|",
    ]
    for group, metrics in sorted(summary["group_metrics"].items()):
        lines.append(
            f"| {group} | {metrics['total']} | {metrics['correct']} | {metrics['accuracy']} |"
        )
    lines += ["", "## 混淆矩阵（期望 → 实际）", "| expected | chosen | count |", "|---|---|---|"]
    for row in summary["confusion_matrix"]:
        lines.append(f"| {row['expected']} | {row['chosen']} | {row['count']} |")
    lines += ["", "## 错误明细"]
    for group, metrics in sorted(summary["group_metrics"].items()):
        if metrics["misclassified"]:
            lines.append(f"### {group}")
            for item in metrics["misclassified"]:
                lines.append(
                    f"- `{item['case_id']}`：期望 {item['expected']}，实际 {item['chosen']}（{item['query'][:40]}）"
                )
    return "\n".join(lines) + "\n"


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _validate_run_scope(
    case_ids: list[str],
    limit: int | None,
    allow_full: bool,
) -> None:
    if case_ids or limit is not None or allow_full:
        return
    raise RuntimeError(
        "refusing to run the full routing eval by default; "
        "pass --case-ids, --limit, or --allow-full."
    )


def _resolve_outputs(
    jsonl_output: Path | None,
    markdown_output: Path | None,
) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    resolved_jsonl = jsonl_output or DEFAULT_REPORT_DIR / f"{timestamp}.jsonl"
    resolved_markdown = markdown_output or DEFAULT_REPORT_DIR / f"{timestamp}.md"
    resolved_jsonl.parent.mkdir(parents=True, exist_ok=True)
    resolved_markdown.parent.mkdir(parents=True, exist_ok=True)
    return resolved_jsonl, resolved_markdown


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())