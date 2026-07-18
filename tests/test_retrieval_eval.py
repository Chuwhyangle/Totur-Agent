"""v0.4 RAG 检索评测逻辑测试。"""

from __future__ import annotations

from pathlib import Path

from app.repositories.knowledge_repository import KnowledgeEntry, KnowledgeHit
from app.services.retrieval_eval import (
    RetrievalEvalCase,
    cosine_similarity,
    evaluate_cases,
    load_eval_cases,
    manual_cosine_check,
    rank_entries_by_cosine,
)


def test_load_eval_cases_reads_jsonl(tmp_path):
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        "\n".join(
            [
                '{"id":"case_1","query":"RAG 怎么检索？","expected_sources":["docs/rag.md"],"expected_title_keywords":["检索"]}',
                '{"id":"case_2","query":"巴黎餐厅推荐","expected_sources":[]}',
            ]
        ),
        encoding="utf-8",
    )

    cases = load_eval_cases(eval_file)

    assert cases == [
        RetrievalEvalCase(
            case_id="case_1",
            query="RAG 怎么检索？",
            expected_sources=["docs/rag.md"],
            expected_title_keywords=["检索"],
            notes="",
        ),
        RetrievalEvalCase(
            case_id="case_2",
            query="巴黎餐厅推荐",
            expected_sources=[],
            expected_title_keywords=[],
            notes="",
        ),
    ]
    assert cases[1].is_negative is True


def test_evaluate_cases_reports_recall_mrr_and_negative_accuracy():
    cases = [
        RetrievalEvalCase(
            case_id="positive_top_2",
            query="RAG",
            expected_sources=["docs/rag.md"],
            expected_title_keywords=[],
        ),
        RetrievalEvalCase(
            case_id="positive_miss",
            query="SQLite",
            expected_sources=["docs/sqlite.md"],
            expected_title_keywords=[],
        ),
        RetrievalEvalCase(
            case_id="negative_clear",
            query="巴黎餐厅",
            expected_sources=[],
            expected_title_keywords=[],
        ),
    ]

    def search(query: str, top_k: int) -> list[KnowledgeHit]:
        hits = {
            "RAG": [
                KnowledgeHit("wrong", "docs/other.md", "", 0.91),
                KnowledgeHit("right", "docs/rag.md", "", 0.82),
            ],
            "SQLite": [
                KnowledgeHit("wrong", "docs/other.md", "", 0.9),
            ],
            "巴黎餐厅": [
                KnowledgeHit("below threshold", "docs/rag.md", "", 0.2),
            ],
        }
        return hits[query][:top_k]

    summary = evaluate_cases(cases, search=search, top_k=3, threshold=0.35)

    assert summary["metrics"] == {
        "total_cases": 3,
        "positive_cases": 2,
        "negative_cases": 1,
        "top_k": 3,
        "threshold": 0.35,
        "recall_at_k": 0.5,
        "mrr": 0.25,
        "negative_accuracy": 1.0,
        "overall_accuracy": 0.6667,
    }
    assert summary["results"][0]["rank"] == 2
    assert summary["results"][1]["passed"] is False
    assert summary["results"][2]["passed"] is True


def test_evaluate_cases_reports_group_metrics():
    cases = [
        RetrievalEvalCase(
            case_id="internal_hit",
            query="internal",
            expected_sources=["docs/internal.md"],
            expected_title_keywords=[],
            group="internal_project",
        ),
        RetrievalEvalCase(
            case_id="external_miss",
            query="external",
            expected_sources=["corpus/external.md"],
            expected_title_keywords=[],
            group="external_self_llm",
        ),
        RetrievalEvalCase(
            case_id="negative_hit",
            query="negative",
            expected_sources=[],
            expected_title_keywords=[],
            group="negative_out_of_scope",
        ),
    ]

    def search(query: str, top_k: int) -> list[KnowledgeHit]:
        hits = {
            "internal": [KnowledgeHit("right", "docs/internal.md", "", 0.9)],
            "external": [KnowledgeHit("wrong", "docs/other.md", "", 0.9)],
            "negative": [KnowledgeHit("unexpected", "docs/other.md", "", 0.9)],
        }
        return hits[query][:top_k]

    summary = evaluate_cases(cases, search=search, top_k=3, threshold=0.35)

    assert summary["group_metrics"]["internal_project"]["recall_at_k"] == 1.0
    assert summary["group_metrics"]["external_self_llm"]["recall_at_k"] == 0.0
    assert summary["group_metrics"]["negative_out_of_scope"]["negative_accuracy"] == 0.0


def test_evaluate_cases_can_require_title_keywords():
    cases = [
        RetrievalEvalCase(
            case_id="title_keyword",
            query="摘要",
            expected_sources=["docs/agent-architecture.md"],
            expected_title_keywords=["滚动摘要"],
        )
    ]

    def search(query: str, top_k: int) -> list[KnowledgeHit]:
        return [
            KnowledgeHit(
                content="摘要更新失败不影响聊天。",
                source="docs/agent-architecture.md",
                title_path="Agent Core > 滚动摘要",
                similarity=0.9,
            )
        ]

    summary = evaluate_cases(cases, search=search, top_k=1, threshold=0.35)

    assert summary["metrics"]["recall_at_k"] == 1.0
    assert summary["results"][0]["passed"] is True


def test_cosine_similarity_and_manual_check_match_chroma_hit():
    entries = [
        KnowledgeEntry(
            chunk_id="docs/a.md#0",
            content="A",
            source="docs/a.md",
            title_path="A",
            embedding=[1.0, 0.0],
        ),
        KnowledgeEntry(
            chunk_id="docs/b.md#0",
            content="B",
            source="docs/b.md",
            title_path="B",
            embedding=[0.0, 1.0],
        ),
    ]

    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert rank_entries_by_cosine([1.0, 0.0], entries)[0][0].source == "docs/a.md"

    check = manual_cosine_check(
        query_embedding=[1.0, 0.0],
        entries=entries,
        chroma_hits=[
            KnowledgeHit(
                content="A",
                source="docs/a.md",
                title_path="A",
                similarity=1.0,
            )
        ],
    )

    assert check["status"] == "ok"
    assert check["similarity_delta"] == 0.0


def test_default_eval_file_has_required_size_and_negative_cases():
    eval_file = Path("tests/data/retrieval_eval.jsonl")

    cases = load_eval_cases(eval_file)
    negative_cases = [case for case in cases if case.is_negative]

    assert 30 <= len(cases) <= 50
    assert len(negative_cases) >= 10
