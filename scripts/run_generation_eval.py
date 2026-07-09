"""Collect v0.4 FR4.6 generation-layer A/B answers."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.chat import ChatRequest
from app.services.generation_eval import (
    GENERATION_EVAL_MODES,
    format_generation_eval_markdown,
    run_generation_eval,
    select_eval_cases,
)
from app.services.retrieval_eval import RetrievalEvalCase, load_eval_cases
from app.services.tutor_agent_service import TutorAgentService


DEFAULT_EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "fr4_6_generation_eval"


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(
        description="Collect tool-only vs seed+tool generation answers."
    )
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument(
        "--case-ids",
        default="",
        help="Comma-separated case ids to run, for example rag_pos_020,rag_pos_010.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N selected cases.",
    )
    parser.add_argument(
        "--include-negative",
        action="store_true",
        help="Include negative cases when selecting by limit.",
    )
    parser.add_argument(
        "--allow-full",
        action="store_true",
        help="Allow running the full eval set. Use sparingly.",
    )
    parser.add_argument(
        "--modes",
        default=",".join(GENERATION_EVAL_MODES),
        help="Comma-separated modes: tool_only,seed_plus_tool.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=20.0,
        help="Pause between chat calls to reduce provider pressure.",
    )
    parser.add_argument(
        "--question-template",
        default="{query}",
        help="Template used as the chat message. Must include {query}.",
    )
    parser.add_argument(
        "--user-prefix",
        default="fr46-eval",
        help="Prefix for isolated eval user ids.",
    )
    parser.add_argument("--jsonl-output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        case_ids = _parse_csv(args.case_ids)
        modes = _parse_csv(args.modes)
        _validate_modes(modes)
        _validate_run_scope(case_ids, args.limit, args.allow_full)
        _validate_question_template(args.question_template)

        repository = KnowledgeRepository()
        if repository.count() == 0:
            raise RuntimeError(
                "knowledge index is empty; run scripts/build_knowledge_index.py first."
            )

        all_cases = load_eval_cases(args.eval_file)
        cases = select_eval_cases(
            all_cases,
            case_ids=case_ids,
            include_negative=args.include_negative or bool(case_ids),
            limit=args.limit,
        )
        if not cases:
            raise RuntimeError("no generation eval cases selected.")

        service = TutorAgentService()
        call_index = {"value": 0}

        def chat(case: RetrievalEvalCase, mode: str):
            call_index["value"] += 1
            print(
                "running {index}/{total}: {case_id} mode={mode}".format(
                    index=call_index["value"],
                    total=len(cases) * len(modes),
                    case_id=case.case_id,
                    mode=mode,
                )
            )
            service.seed_context_enabled = mode == "seed_plus_tool"
            response = service.chat(
                ChatRequest(
                    user_id=f"{args.user_prefix}-{case.case_id}-{mode}",
                    message=args.question_template.format(query=case.query),
                )
            )
            if args.delay_seconds > 0:
                time.sleep(args.delay_seconds)
            return response

        records = run_generation_eval(cases=cases, chat=chat, modes=modes)
        jsonl_output, markdown_output = _resolve_outputs(
            args.jsonl_output,
            args.markdown_output,
        )
        _write_jsonl(jsonl_output, records)
        markdown_output.write_text(
            format_generation_eval_markdown(records),
            encoding="utf-8",
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"生成层评测失败：{exc}", file=sys.stderr)
        return 1

    print(f"jsonl={jsonl_output}")
    print(f"markdown={markdown_output}")
    return 0


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _validate_modes(modes: list[str]) -> None:
    if not modes:
        raise ValueError("at least one generation eval mode is required.")

    unsupported = [mode for mode in modes if mode not in GENERATION_EVAL_MODES]
    if unsupported:
        raise ValueError(f"unsupported generation eval modes: {unsupported}")


def _validate_run_scope(
    case_ids: list[str],
    limit: int | None,
    allow_full: bool,
) -> None:
    if case_ids or limit is not None or allow_full:
        return

    raise RuntimeError(
        "refusing to run the full generation eval by default; "
        "pass --case-ids, --limit, or --allow-full."
    )


def _validate_question_template(template: str) -> None:
    if "{query}" not in template:
        raise ValueError("--question-template must include {query}.")


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

