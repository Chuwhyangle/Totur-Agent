"""v0.4 seed context 检索实验测试。"""

from __future__ import annotations

from app.clients.embedding_client import EmbeddingError
from app.repositories.knowledge_repository import KnowledgeHit
from app.services.rag_seed_context import (
    build_seed_knowledge_context,
    retrieve_seed_knowledge_context,
)


class FakeRepository:
    def __init__(self, hits: list[KnowledgeHit] | None = None, count: int = 1) -> None:
        self.hits = hits or []
        self._count = count

    def count(self) -> int:
        return self._count

    def search(self, query_embedding: list[float], top_k: int) -> list[KnowledgeHit]:
        return self.hits[:top_k]


class FakeEmbeddingClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


class FailingEmbeddingClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("provider down")


def test_build_seed_knowledge_context_formats_hits_with_sources():
    context = build_seed_knowledge_context(
        [
            KnowledgeHit(
                content="分块器按 Markdown 标题切分。",
                source="docs/rag.md",
                title_path="RAG > 分块器",
                similarity=0.91,
            )
        ],
        max_chars=500,
    )

    assert context is not None
    assert context.startswith("[Knowledge Base Context]")
    assert "来源：docs/rag.md" in context
    assert "标题：RAG > 分块器" in context
    assert "相似度：0.9100" in context


def test_build_seed_knowledge_context_respects_max_chars():
    context = build_seed_knowledge_context(
        [
            KnowledgeHit(
                content="很长的内容" * 200,
                source="docs/rag.md",
                title_path="RAG",
                similarity=0.9,
            )
        ],
        max_chars=180,
    )

    assert context is not None
    assert len(context) <= 180
    assert context.endswith("...")


def test_retrieve_seed_knowledge_context_returns_none_when_index_missing():
    context = retrieve_seed_knowledge_context(
        "RAG",
        repository=FakeRepository(count=0),
        embedding_client=FakeEmbeddingClient(),
    )

    assert context is None


def test_retrieve_seed_knowledge_context_filters_low_similarity_hits():
    context = retrieve_seed_knowledge_context(
        "RAG",
        repository=FakeRepository(
            hits=[
                KnowledgeHit(
                    content="低分结果",
                    source="docs/rag.md",
                    title_path="RAG",
                    similarity=0.1,
                )
            ]
        ),
        embedding_client=FakeEmbeddingClient(),
    )

    assert context is None


def test_retrieve_seed_knowledge_context_fails_open_on_embedding_error():
    context = retrieve_seed_knowledge_context(
        "RAG",
        repository=FakeRepository(
            hits=[
                KnowledgeHit(
                    content="不会走到这里",
                    source="docs/rag.md",
                    title_path="RAG",
                    similarity=0.9,
                )
            ]
        ),
        embedding_client=FailingEmbeddingClient(),
    )

    assert context is None


def test_retrieve_seed_knowledge_context_returns_formatted_context():
    context = retrieve_seed_knowledge_context(
        "RAG",
        repository=FakeRepository(
            hits=[
                KnowledgeHit(
                    content="分块器按 Markdown 标题切分。",
                    source="docs/rag.md",
                    title_path="RAG > 分块器",
                    similarity=0.9,
                )
            ]
        ),
        embedding_client=FakeEmbeddingClient(),
    )

    assert context is not None
    assert "docs/rag.md" in context
