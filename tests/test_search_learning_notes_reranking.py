"""Integration tests for reranking inside search_learning_notes."""

from __future__ import annotations

from app.clients.reranker_client import RerankerError, RerankScore
from app.repositories.knowledge_repository import KnowledgeHit
from app.services.agent.tools import search_learning_notes as tool_module
from app.services.reranking import RerankingService


class FakeRepository:
    def count(self) -> int:
        return 10


class FakeEmbeddingClient:
    def embed_texts(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeRerankerClient:
    provider = "fake-provider"
    model = "fake-model"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def rerank(self, query, candidates, *, top_n):
        self.calls.append((query, candidates, top_n))
        if self.fail:
            raise RerankerError("rerank_timeout")
        return [RerankScore(candidate.index, float(candidate.index)) for candidate in candidates]


def _hits(count: int = 4) -> list[KnowledgeHit]:
    return [
        KnowledgeHit(
            content=f"body-{index}",
            source=f"docs/{index}.md",
            title_path=f"Title {index}",
            similarity=0.9 - index * 0.05,
        )
        for index in range(count)
    ]


def _arrange(monkeypatch, hits):
    observed = {}
    monkeypatch.setattr(tool_module, "_repository", FakeRepository())
    monkeypatch.setattr(tool_module, "_embedding_client", FakeEmbeddingClient())
    monkeypatch.setattr(tool_module, "ENABLE_SUBJECT_SHARDING", False)

    def retrieve(**kwargs):
        observed.update(kwargs)
        return hits[: kwargs["top_k"]]

    monkeypatch.setattr(tool_module, "_retrieve_hits", retrieve)
    return observed


def test_reranking_disabled_preserves_existing_output_and_does_not_load_service(monkeypatch):
    hits = _hits()
    observed = _arrange(monkeypatch, hits)
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", False)
    monkeypatch.setattr(
        tool_module,
        "_get_reranking_service",
        lambda: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )

    result = tool_module.search_learning_notes("query", limit=2)

    assert result["ok"] is True
    assert [item["source"] for item in result["results"]] == ["docs/0.md", "docs/1.md"]
    assert result["summary"] == {"returned_count": 2}
    assert observed["top_k"] == 2
    assert all("rerank_score" not in item for item in result["results"] )


def test_reranking_enabled_retrieves_ten_and_returns_at_most_three(monkeypatch):
    hits = _hits(10)
    observed = _arrange(monkeypatch, hits)
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", True)
    monkeypatch.setattr(tool_module, "RERANK_CANDIDATE_K", 10)
    client = FakeRerankerClient()
    service = RerankingService(enabled=True, client_factory=lambda: client)
    monkeypatch.setattr(tool_module, "_reranking_service", service)

    result = tool_module.search_learning_notes("query", limit=5)

    assert observed["top_k"] == 10
    assert [item["source"] for item in result["results"]] == [
        "docs/9.md",
        "docs/8.md",
        "docs/7.md",
    ]
    assert result["results"][0]["similarity"] == hits[9].similarity
    assert result["results"][0]["rerank_score"] == 9.0
    assert result["summary"]["candidate_count"] == 10
    assert result["summary"]["rerank_applied"] is True
    assert result["summary"]["rerank_provider"] == "fake-provider"
    assert result["summary"]["rerank_model"] == "fake-model"
    assert len(client.calls) == 1


def test_reranking_timeout_keeps_tool_ok_and_original_order(monkeypatch):
    hits = _hits(4)
    _arrange(monkeypatch, hits)
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", True)
    client = FakeRerankerClient(fail=True)
    service = RerankingService(enabled=True, client_factory=lambda: client)
    monkeypatch.setattr(tool_module, "_reranking_service", service)

    result = tool_module.search_learning_notes("query")

    assert result["ok"] is True
    assert [item["source"] for item in result["results"]] == [
        "docs/0.md",
        "docs/1.md",
        "docs/2.md",
    ]
    assert result["summary"]["rerank_applied"] is False
    assert result["summary"]["rerank_fallback_reason"] == "rerank_timeout"
    assert all("rerank_score" not in item for item in result["results"] )
