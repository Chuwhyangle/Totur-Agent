"""Generation-layer A/B helpers for v0.4 FR4.6."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.schemas.chat import ChatResponse
from app.services.retrieval_eval import RetrievalEvalCase


GENERATION_EVAL_MODES = ("tool_only", "seed_plus_tool")

GENERATION_SCORE_FIELDS: list[dict[str, Any]] = [
    {
        "name": "source_faithfulness",
        "max_score": 2,
        "description": "Whether the answer stays grounded in retrieved project notes.",
    },
    {
        "name": "answer_completeness",
        "max_score": 2,
        "description": "Whether the answer covers the core question fully.",
    },
    {
        "name": "tool_efficiency",
        "max_score": 2,
        "description": "Whether tool use is appropriate, neither missing nor wasteful.",
    },
    {
        "name": "citation_integrity",
        "max_score": 2,
        "description": "Whether citations are real and not fabricated.",
    },
]

ChatEvalFunc = Callable[[RetrievalEvalCase, str], ChatResponse]


def select_eval_cases(
    cases: Sequence[RetrievalEvalCase],
    case_ids: Sequence[str] | None = None,
    include_negative: bool = True,
    limit: int | None = None,
) -> list[RetrievalEvalCase]:
    """Select generation eval cases, preserving explicit case-id order."""

    if case_ids:
        by_id = {case.case_id: case for case in cases}
        missing_ids = [case_id for case_id in case_ids if case_id not in by_id]
        if missing_ids:
            raise ValueError(f"unknown generation eval case ids: {missing_ids}")
        selected = [by_id[case_id] for case_id in case_ids]
    else:
        selected = list(cases)

    if not include_negative:
        selected = [case for case in selected if not case.is_negative]

    if limit is not None:
        selected = selected[: max(0, limit)]

    return selected


def run_generation_eval(
    cases: Sequence[RetrievalEvalCase],
    chat: ChatEvalFunc,
    modes: Sequence[str] = GENERATION_EVAL_MODES,
) -> list[dict[str, Any]]:
    """Collect model answers for every case in every requested eval mode."""

    records: list[dict[str, Any]] = []
    for case in cases:
        for mode in modes:
            _validate_mode(mode)
            response = chat(case, mode)
            records.append(
                build_generation_eval_record(
                    case=case,
                    mode=mode,
                    response=response,
                )
            )

    return records


def build_generation_eval_record(
    case: RetrievalEvalCase,
    mode: str,
    response: ChatResponse,
) -> dict[str, Any]:
    """Convert one ChatResponse into a durable manual-scoring record."""

    _validate_mode(mode)
    return {
        "id": case.case_id,
        "query": case.query,
        "mode": mode,
        "negative": case.is_negative,
        "expected_sources": case.expected_sources,
        "expected_title_keywords": case.expected_title_keywords,
        "notes": case.notes,
        "reply": _model_to_dict(response.reply),
        "tool_trace": _model_to_dict(response.tool_trace),
        "manual_scores": {
            field["name"]: None for field in GENERATION_SCORE_FIELDS
        },
        "manual_notes": "",
    }


def summarize_manual_scores(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize filled manual score fields by eval mode."""

    summary: dict[str, Any] = {}
    modes = _ordered_modes(records)
    for mode in modes:
        mode_records = [record for record in records if record.get("mode") == mode]
        scored_records = [
            record for record in mode_records if _record_has_complete_scores(record)
        ]
        total_scores = [_record_total_score(record) for record in scored_records]
        summary[mode] = {
            "records": len(mode_records),
            "scored_records": len(scored_records),
            "average_total_score": _average(total_scores),
            "average_field_scores": _average_field_scores(scored_records),
        }

    summary["winner"] = _winner(summary)
    return summary


def format_generation_eval_markdown(records: Sequence[dict[str, Any]]) -> str:
    """Format collected generation eval records for manual review."""

    lines = [
        "# v0.4 FR4.6 生成层 A/B 评测",
        "",
        "## 评分表",
        "",
        "| 字段 | 分值 | 说明 |",
        "|---|---:|---|",
    ]
    for field in GENERATION_SCORE_FIELDS:
        lines.append(
            "| {name} | 0-{max_score} | {description} |".format(**field)
        )

    for case_id in _ordered_case_ids(records):
        case_records = [record for record in records if record.get("id") == case_id]
        first_record = case_records[0]
        lines.extend(
            [
                "",
                f"## {case_id}",
                "",
                f"Query: {first_record.get('query', '')}",
                "",
                "Expected sources: "
                + ", ".join(first_record.get("expected_sources") or []),
            ]
        )
        for record in case_records:
            reply = record.get("reply") if isinstance(record.get("reply"), dict) else {}
            tool_trace = (
                record.get("tool_trace")
                if isinstance(record.get("tool_trace"), dict)
                else {}
            )
            lines.extend(
                [
                    "",
                    f"### {record.get('mode')}",
                    "",
                    f"Tool used: {bool(tool_trace.get('used'))}",
                    "",
                    "Answer:",
                    "",
                    str(reply.get("answer") or ""),
                    "",
                    "Manual scores:",
                ]
            )
            scores = (
                record.get("manual_scores")
                if isinstance(record.get("manual_scores"), dict)
                else {}
            )
            for field in GENERATION_SCORE_FIELDS:
                score = scores.get(field["name"])
                lines.append(
                    f"- {field['name']}: {'' if score is None else score}"
                )
            lines.append(f"- notes: {record.get('manual_notes') or ''}")

    return "\n".join(lines).rstrip() + "\n"


def _model_to_dict(model: Any) -> dict[str, Any]:
    """Support both Pydantic v1 and v2 model objects."""

    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _validate_mode(mode: str) -> None:
    if mode not in GENERATION_EVAL_MODES:
        raise ValueError(f"unsupported generation eval mode: {mode}")


def _ordered_modes(records: Sequence[dict[str, Any]]) -> list[str]:
    modes = [
        mode
        for mode in GENERATION_EVAL_MODES
        if any(record.get("mode") == mode for record in records)
    ]
    extras = [
        str(record.get("mode"))
        for record in records
        if record.get("mode") not in GENERATION_EVAL_MODES
    ]
    for mode in extras:
        if mode not in modes:
            modes.append(mode)
    return modes


def _ordered_case_ids(records: Sequence[dict[str, Any]]) -> list[str]:
    case_ids: list[str] = []
    for record in records:
        case_id = str(record.get("id") or "")
        if case_id and case_id not in case_ids:
            case_ids.append(case_id)
    return case_ids


def _record_has_complete_scores(record: dict[str, Any]) -> bool:
    scores = record.get("manual_scores")
    if not isinstance(scores, dict):
        return False

    return all(
        _score_value(scores.get(field["name"])) is not None
        for field in GENERATION_SCORE_FIELDS
    )


def _record_total_score(record: dict[str, Any]) -> int:
    scores = record["manual_scores"]
    return sum(int(scores[field["name"]]) for field in GENERATION_SCORE_FIELDS)


def _average_field_scores(records: Sequence[dict[str, Any]]) -> dict[str, float]:
    return {
        field["name"]: _average(
            [int(record["manual_scores"][field["name"]]) for record in records]
        )
        for field in GENERATION_SCORE_FIELDS
    }


def _score_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        score = int(value)
    except (TypeError, ValueError):
        return None

    if 0 <= score <= 2:
        return score
    return None


def _average(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _winner(summary: dict[str, Any]) -> str | None:
    scored = {
        mode: data
        for mode, data in summary.items()
        if isinstance(data, dict) and data.get("scored_records")
    }
    if len(scored) < 2:
        return None

    ranked = sorted(
        scored.items(),
        key=lambda item: item[1]["average_total_score"],
        reverse=True,
    )
    if (
        len(ranked) > 1
        and ranked[0][1]["average_total_score"] == ranked[1][1]["average_total_score"]
    ):
        return "tie"
    return ranked[0][0]
