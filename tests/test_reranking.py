"""Tests for stable reranking and lossless fallback."""

from __future__ import annotations

from app.clients.reranker_client import RerankerError, RerankScore
from app.repositories.knowledge_repository import KnowledgeHit
from app.services.reranking import RerankingService


def _hits() -> list[KnowledgeHit]:
    return [
        KnowledgeHit("first body", "docs/a.md", "A", 0.9),
        KnowledgeHit("second body", "docs/b.md", "B", 0.8),
        KnowledgeHit("third body", "docs/c.md", "C", 0.7),
    ]


class FakeClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self, scores: list[RerankScore] | None = None, error: RerankerError | None = None):
        self.scores = scores or []
        self.error = error
        self.calls = []

    def rerank(self, query, candidates, *, top_n):
        self.calls.append((query, candidates, top_n))
        if self.error is not None:
            raise self.error
        return self.scores


def test_disabled_reranking_does_not_load_client_and_preserves_order():
    def forbidden_factory():
        raise AssertionError("disabled reranking must not load a client")

    service = RerankingService(enabled=False, client_factory=forbidden_factory)
    outcome = service.rerank("query", _hits(), top_n=2)

    assert outcome.hits == _hits()[:2]
    assert outcome.applied is False
    assert outcome.scores_by_index == {}


def test_empty_and_single_candidate_do_not_call_provider():
    client = FakeClient()
    service = RerankingService(enabled=True, client_factory=lambda: client)

    empty = service.rerank("query", [], top_n=3)
    single = service.rerank("query", _hits()[:1], top_n=3)

    assert empty.hits == []
    assert single.hits == _hits()[:1]
    assert client.calls == []


def test_reranking_can_promote_lower_hit_and_preserves_hit_data():
    client = FakeClient(
        [RerankScore(0, 0.1), RerankScore(1, 0.2), RerankScore(2, 0.99)]
    )
    original = _hits()
    service = RerankingService(enabled=True, client_factory=lambda: client)

    outcome = service.rerank("query", original, top_n=2)

    assert outcome.hits == [original[2], original[1]]
    assert outcome.scores_by_index == {0: 0.1, 1: 0.2, 2: 0.99}
    assert outcome.applied is True
    assert outcome.provider == "fake"
    assert outcome.model == "fake-model"
    assert len(client.calls) == 1
    assert client.calls[0][2] == 3


def test_equal_rerank_scores_use_retrieval_score_then_original_index():
    hits = [
        KnowledgeHit("a", "a", "a", 0.8),
        KnowledgeHit("b", "b", "b", 0.9),
        KnowledgeHit("c", "c", "c", 0.9),
    ]
    client = FakeClient([RerankScore(0, 0.5), RerankScore(1, 0.5), RerankScore(2, 0.5)])
    service = RerankingService(enabled=True, client_factory=lambda: client)

    outcome = service.rerank("query", hits, top_n=3)

    assert outcome.hits == [hits[1], hits[2], hits[0]]


def test_provider_failure_falls_back_to_original_order():
    client = FakeClient(error=RerankerError("rerank_timeout"))
    service = RerankingService(enabled=True, client_factory=lambda: client)

    outcome = service.rerank("query", _hits(), top_n=2)

    assert outcome.hits == _hits()[:2]
    assert outcome.applied is False
    assert outcome.fallback_reason == "rerank_timeout"
    assert outcome.scores_by_index == {}


def test_invalid_fake_client_response_also_falls_back():
    client = FakeClient([RerankScore(0, 0.9)])
    service = RerankingService(enabled=True, client_factory=lambda: client)

    outcome = service.rerank("query", _hits(), top_n=3)

    assert outcome.hits == _hits()
    assert outcome.fallback_reason == "rerank_invalid_response"


def test_candidate_text_uses_title_and_deterministic_truncation():
    hits = [
        KnowledgeHit("abcdef", "docs/a.md", "Title A", 0.9),
        KnowledgeHit("uvwxyz", "docs/b.md", "Title B", 0.8),
    ]
    client = FakeClient([RerankScore(0, 0.9), RerankScore(1, 0.8)])
    service = RerankingService(
        enabled=True,
        client_factory=lambda: client,
        max_text_chars=3,
    )

    service.rerank("query", hits, top_n=2)

    candidates = client.calls[0][1]
    assert [candidate.text for candidate in candidates] == ["Title A\nabc", "Title B\nuvw"]
    assert [candidate.retrieval_score for candidate in candidates] == [0.9, 0.8]


def test_service_limits_candidates_and_final_results():
    hits = [KnowledgeHit(str(i), str(i), str(i), 1 - i / 100) for i in range(12)]
    client = FakeClient([RerankScore(i, float(i)) for i in range(10)])
    service = RerankingService(enabled=True, client_factory=lambda: client, candidate_k=10)

    outcome = service.rerank("query", hits, top_n=3)

    assert len(client.calls[0][1]) == 10
    assert len(outcome.hits) == 3
    assert [hit.source for hit in outcome.hits] == ["9", "8", "7"]


def test_candidate_text_does_not_send_absolute_source_path():
    hits = [
        KnowledgeHit("body-a", "C:/private/user/docs/a.md", "", 0.9),
        KnowledgeHit("body-b", "/home/user/private/b.md", "", 0.8),
    ]
    client = FakeClient([RerankScore(0, 0.9), RerankScore(1, 0.8)])
    service = RerankingService(enabled=True, client_factory=lambda: client)

    service.rerank("query", hits, top_n=2)

    texts = [candidate.text for candidate in client.calls[0][1]]
    assert texts == ["a.md\nbody-a", "b.md\nbody-b"]
    assert all("private" not in text for text in texts)
