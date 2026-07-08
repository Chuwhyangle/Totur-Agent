"""v0.4 Hybrid 检索测试。"""

from __future__ import annotations

from app.repositories.knowledge_repository import KnowledgeEntry, KnowledgeHit
from app.services.hybrid_retriever import hybrid_search, tokenize_for_bm25


class FakeHybridRepository:
    """给 hybrid_search 提供最小 repository 边界。"""

    def __init__(
        self,
        entries: list[KnowledgeEntry],
        vector_hits: list[KnowledgeHit] | None = None,
    ) -> None:
        self.entries = entries
        self.vector_hits = vector_hits or []

    def search(self, query_embedding: list[float], top_k: int) -> list[KnowledgeHit]:
        return self.vector_hits[:top_k]

    def list_entries(self, include_embeddings: bool = False) -> list[KnowledgeEntry]:
        return self.entries


def test_tokenize_for_bm25_handles_mixed_chinese_and_english():
    tokens = tokenize_for_bm25("v0.4 Hybrid 检索 + BM25 / RAG")

    assert tokens == ["v0.4", "hybrid", "检索", "+", "bm25", "rag"]


def test_hybrid_search_adds_bm25_candidates_when_vector_search_misses():
    entries = [
        KnowledgeEntry(
            chunk_id="docs/rag.md#0",
            content="Hybrid 检索会融合 BM25 和向量分数。",
            source="docs/rag.md",
            title_path="v0.4 > Hybrid 检索",
        ),
        KnowledgeEntry(
            chunk_id="docs/api.md#0",
            content="POST /chat 会保存对话。",
            source="docs/api.md",
            title_path="API",
        ),
    ]
    repository = FakeHybridRepository(entries=entries)

    hits = hybrid_search(
        repository=repository,
        query="Hybrid BM25 检索",
        query_embedding=[1.0, 0.0],
        top_k=1,
    )

    assert len(hits) == 1
    assert hits[0].source == "docs/rag.md"
    assert hits[0].similarity > 0


def test_hybrid_search_preserves_strong_vector_hit_score():
    entries = [
        KnowledgeEntry(
            chunk_id="docs/rag.md#0",
            content="RAG 分块器说明。",
            source="docs/rag.md",
            title_path="RAG",
        )
    ]
    vector_hits = [
        KnowledgeHit(
            content="RAG 分块器说明。",
            source="docs/rag.md",
            title_path="RAG",
            similarity=0.92,
        )
    ]
    repository = FakeHybridRepository(entries=entries, vector_hits=vector_hits)

    hits = hybrid_search(
        repository=repository,
        query="完全不相关的词面查询",
        query_embedding=[1.0, 0.0],
        top_k=1,
    )

    assert hits[0].source == "docs/rag.md"
    assert hits[0].similarity == 0.92
