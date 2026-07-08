"""Seed-context retrieval for v0.4 FR4.6 experiments."""

from __future__ import annotations

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.repositories.knowledge_repository import KnowledgeHit, KnowledgeRepository
from app.services.rag_settings import (
    RAG_SEED_MAX_CHARS,
    RAG_SEED_TOP_K,
    SIMILARITY_THRESHOLD,
)


def retrieve_seed_knowledge_context(
    query: str,
    repository: KnowledgeRepository | None = None,
    embedding_client: EmbeddingClient | None = None,
    top_k: int = RAG_SEED_TOP_K,
    max_chars: int = RAG_SEED_MAX_CHARS,
) -> str | None:
    """Pre-retrieve note chunks and format them as optional model context."""

    if not isinstance(query, str) or not query.strip():
        return None

    repository = repository or KnowledgeRepository()
    if repository.count() == 0:
        return None

    try:
        embedding_client = embedding_client or EmbeddingClient()
        query_embedding = embedding_client.embed_texts([query.strip()])[0]
    except (EmbeddingError, IndexError, RuntimeError):
        return None

    hits = [
        hit
        for hit in repository.search(query_embedding=query_embedding, top_k=top_k)
        if hit.similarity >= SIMILARITY_THRESHOLD
    ]
    return build_seed_knowledge_context(hits, max_chars=max_chars)


def build_seed_knowledge_context(
    hits: list[KnowledgeHit],
    max_chars: int = RAG_SEED_MAX_CHARS,
) -> str | None:
    """Format retrieval hits into a compact system message."""

    if not hits or max_chars <= 0:
        return None

    header = (
        "[Knowledge Base Context]\n"
        "以下是根据本轮问题预检索到的学习笔记片段。它们是可引用依据，"
        "如果回答引用其中内容，句末必须标注（来源：文件名）。"
    )
    context = header

    for index, hit in enumerate(hits, 1):
        block = _format_hit_block(index, hit)
        next_context = f"{context}\n\n{block}"
        if len(next_context) <= max_chars:
            context = next_context
            continue

        remaining = max_chars - len(context) - 5
        if remaining > 80:
            context = f"{context}\n\n{block[:remaining].rstrip()}..."
        break

    return context if context != header else None


def _format_hit_block(index: int, hit: KnowledgeHit) -> str:
    """Format one hit for seed context."""

    title = hit.title_path or hit.source
    return (
        f"{index}. 来源：{hit.source}\n"
        f"标题：{title}\n"
        f"相似度：{hit.similarity:.4f}\n"
        f"内容：{hit.content.strip()}"
    )
