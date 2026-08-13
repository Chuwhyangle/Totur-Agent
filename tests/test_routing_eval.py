"""FR-5: 路由评测脚本的纯逻辑单元测试。"""

from __future__ import annotations

from app.services.retrieval_eval import RetrievalEvalCase
from scripts.run_routing_eval import (
    _is_correct,
    _select_cases,
    _summarize,
)


def _case(
    case_id: str,
    *,
    expected_tool: str | None = None,
    expected_tools: tuple[str, ...] = (),
    expected_sources: list[str] | None = None,
    group: str = "default",
) -> RetrievalEvalCase:
    return RetrievalEvalCase(
        case_id=case_id,
        query=f"query-{case_id}",
        expected_sources=expected_sources or [],
        expected_title_keywords=[],
        group=group,
        expected_tool=expected_tool,
        expected_tools=expected_tools,
    )


def test_is_correct_single_tool_exact_match():
    case = _case("c1", expected_tool="search_learning_notes")
    assert _is_correct(case, {"search_learning_notes"}) is True


def test_is_correct_single_tool_wrong_tool():
    case = _case("c1", expected_tool="search_learning_notes")
    assert _is_correct(case, {"search_job_descriptions"}) is False


def test_is_correct_single_tool_extra_tool_rejected():
    case = _case("c1", expected_tool="search_learning_notes")
    assert _is_correct(case, {"search_learning_notes", "search_job_descriptions"}) is False


def test_is_correct_single_tool_no_tool_rejected():
    case = _case("c1", expected_tool="search_learning_notes")
    assert _is_correct(case, set()) is False


def test_is_correct_multi_tool_exact_match():
    case = _case(
        "c2",
        expected_tools=("search_job_descriptions", "search_learning_notes"),
    )
    assert _is_correct(case, {"search_learning_notes", "search_job_descriptions"}) is True


def test_is_correct_negative_requires_no_tool():
    case = _case("neg1", expected_tool=None)
    assert _is_correct(case, set()) is True
    assert _is_correct(case, {"search_learning_notes"}) is False


def test_select_cases_by_ids():
    cases = [_case("a"), _case("b"), _case("c")]
    selected = _select_cases(cases, case_ids=["c", "a"], limit=None)
    assert [case.case_id for case in selected] == ["c", "a"]


def test_select_cases_unknown_id_raises():
    cases = [_case("a")]
    try:
        _select_cases(cases, case_ids=["zzz"], limit=None)
        assert False, "should raise"
    except ValueError:
        pass


def test_select_cases_limit():
    cases = [_case("a"), _case("b"), _case("c")]
    selected = _select_cases(cases, case_ids=[], limit=2)
    assert [case.case_id for case in selected] == ["a", "b"]


def test_summarize_computes_overall_and_group_accuracy():
    records = [
        {"case_id": "a", "group": "g1", "query": "q", "expected_tool": "t1",
         "expected_tools": [], "chosen_tools": ["t1"], "correct": True},
        {"case_id": "b", "group": "g1", "query": "q", "expected_tool": "t1",
         "expected_tools": [], "chosen_tools": ["t2"], "correct": False},
        {"case_id": "c", "group": "g2", "query": "q", "expected_tool": None,
         "expected_tools": [], "chosen_tools": [], "correct": True},
    ]
    summary = _summarize(records)

    assert summary["total"] == 3
    assert summary["correct"] == 2
    assert summary["overall_accuracy"] == round(2 / 3, 4)
    assert summary["group_metrics"]["g1"]["accuracy"] == 0.5
    assert summary["group_metrics"]["g2"]["accuracy"] == 1.0
    assert summary["group_metrics"]["g1"]["misclassified"][0]["case_id"] == "b"
    # 混淆矩阵
    pairs = {(row["expected"], row["chosen"]) for row in summary["confusion_matrix"]}
    assert ("t1", "t2") in pairs