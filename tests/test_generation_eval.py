"""v0.4 FR4.6 generation-layer A/B evaluation tests."""

from __future__ import annotations

from app.schemas.chat import ChatResponse, ToolTrace, TutorReply
from app.services.generation_eval import (
    GENERATION_EVAL_MODES,
    GENERATION_SCORE_FIELDS,
    build_generation_eval_record,
    format_generation_eval_markdown,
    run_generation_eval,
    select_eval_cases,
    summarize_manual_scores,
)
from app.services.retrieval_eval import RetrievalEvalCase


def make_case(case_id: str, query: str, expected_sources: list[str]):
    return RetrievalEvalCase(
        case_id=case_id,
        query=query,
        expected_sources=expected_sources,
        expected_title_keywords=[],
        notes="sample note",
    )


def make_response(answer: str, used_tools: bool = False) -> ChatResponse:
    return ChatResponse(
        user_id="eval-user",
        session_id=1,
        message="question",
        reply=TutorReply(
            answer=answer,
            next_task="next",
            exercise="exercise",
            checkpoints=["checkpoint"],
        ),
        tool_trace=ToolTrace(used=used_tools, calls=[]),
    )


def test_select_eval_cases_preserves_requested_order():
    cases = [
        make_case("rag_pos_001", "Q1", ["docs/a.md"]),
        make_case("rag_pos_002", "Q2", ["docs/b.md"]),
        make_case("rag_neg_001", "Q3", []),
    ]

    selected = select_eval_cases(
        cases,
        case_ids=["rag_pos_002", "rag_pos_001"],
        include_negative=False,
    )

    assert [case.case_id for case in selected] == ["rag_pos_002", "rag_pos_001"]


def test_build_generation_eval_record_includes_score_template():
    case = make_case("rag_pos_001", "RAG 为什么是工具？", ["docs/rag.md"])

    record = build_generation_eval_record(
        case=case,
        mode="tool_only",
        response=make_response("RAG 是第三个工具。", used_tools=True),
    )

    assert record["id"] == "rag_pos_001"
    assert record["mode"] == "tool_only"
    assert record["query"] == "RAG 为什么是工具？"
    assert record["reply"]["answer"] == "RAG 是第三个工具。"
    assert record["tool_trace"]["used"] is True
    assert record["manual_scores"] == {
        field["name"]: None for field in GENERATION_SCORE_FIELDS
    }
    assert record["manual_notes"] == ""


def test_run_generation_eval_collects_each_case_in_both_modes():
    cases = [make_case("rag_pos_001", "RAG 为什么是工具？", ["docs/rag.md"])]
    calls: list[tuple[str, str]] = []

    def fake_chat(case: RetrievalEvalCase, mode: str) -> ChatResponse:
        calls.append((case.case_id, mode))
        return make_response(f"{mode} answer")

    records = run_generation_eval(cases, chat=fake_chat)

    assert calls == [
        ("rag_pos_001", GENERATION_EVAL_MODES[0]),
        ("rag_pos_001", GENERATION_EVAL_MODES[1]),
    ]
    assert [record["reply"]["answer"] for record in records] == [
        "tool_only answer",
        "seed_plus_tool answer",
    ]


def test_summarize_manual_scores_reports_mode_averages_and_winner():
    records = [
        {
            "mode": "tool_only",
            "manual_scores": {
                "source_faithfulness": 2,
                "answer_completeness": 1,
                "tool_efficiency": 1,
                "citation_integrity": 1,
            },
        },
        {
            "mode": "seed_plus_tool",
            "manual_scores": {
                "source_faithfulness": 2,
                "answer_completeness": 2,
                "tool_efficiency": 2,
                "citation_integrity": 2,
            },
        },
    ]

    summary = summarize_manual_scores(records)

    assert summary["tool_only"]["scored_records"] == 1
    assert summary["tool_only"]["average_total_score"] == 5.0
    assert summary["seed_plus_tool"]["average_total_score"] == 8.0
    assert summary["winner"] == "seed_plus_tool"


def test_format_generation_eval_markdown_includes_rubric_and_records():
    case = make_case("rag_pos_001", "RAG 为什么是工具？", ["docs/rag.md"])
    record = build_generation_eval_record(
        case=case,
        mode="tool_only",
        response=make_response("RAG 是第三个工具。", used_tools=True),
    )

    markdown = format_generation_eval_markdown([record])

    assert "# v0.4 FR4.6 生成层 A/B 评测" in markdown
    assert "| source_faithfulness | 0-2 |" in markdown
    assert "## rag_pos_001" in markdown
    assert "### tool_only" in markdown
    assert "RAG 是第三个工具。" in markdown
    assert "- source_faithfulness: " in markdown
