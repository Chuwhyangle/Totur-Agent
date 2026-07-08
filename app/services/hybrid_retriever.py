"""Hybrid retrieval for learning notes."""

from __future__ import annotations

from collections import Counter
import math
import re
from typing import Protocol

from app.repositories.knowledge_repository import KnowledgeEntry, KnowledgeHit
from app.services.rag_settings import (
    HYBRID_BM25_WEIGHT,
    HYBRID_CANDIDATE_MULTIPLIER,
    HYBRID_VECTOR_WEIGHT,
)

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - exercised only when optional dep is absent.
    BM25Okapi = None


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_+#.-]+")


class HybridRepository(Protocol):
    """Repository methods needed by hybrid retrieval."""

    def search(self, query_embedding: list[float], top_k: int) -> list[KnowledgeHit]:
        """Vector search."""

    def list_entries(self, include_embeddings: bool = False) -> list[KnowledgeEntry]:
        """List indexed entries."""


def hybrid_search(
    repository: HybridRepository,
    query: str,
    query_embedding: list[float],
    top_k: int,
) -> list[KnowledgeHit]:
    """Fuse vector search with BM25 lexical search."""

    if top_k <= 0:
        return []

    candidate_k = max(top_k, top_k * HYBRID_CANDIDATE_MULTIPLIER)
    entries = repository.list_entries(include_embeddings=False)
    if not entries:
        return []

    vector_hits = repository.search(query_embedding=query_embedding, top_k=candidate_k)
    vector_by_key = {_hit_key(hit): hit for hit in vector_hits}
    vector_scores = {
        _hit_key(hit): _clamp_score(hit.similarity)
        for hit in vector_hits
    }

    bm25_scores = _bm25_scores(query=query, entries=entries)
    bm25_by_key = {
        _entry_key(entry): score
        for entry, score in zip(entries, _normalize_scores(bm25_scores))
        if score > 0
    }
    entry_by_key = {_entry_key(entry): entry for entry in entries}

    candidate_keys = set(vector_scores) | set(_top_bm25_keys(bm25_by_key, candidate_k))
    hits: list[KnowledgeHit] = []
    for key in candidate_keys:
        vector_score = vector_scores.get(key, 0.0)
        bm25_score = bm25_by_key.get(key, 0.0)
        fused_score = (HYBRID_VECTOR_WEIGHT * vector_score) + (
            HYBRID_BM25_WEIGHT * bm25_score
        )
        # Preserve strong vector matches while still allowing a strong lexical-only
        # candidate to pass the shared threshold during eval.
        hybrid_score = max(vector_score, fused_score)

        vector_hit = vector_by_key.get(key)
        if vector_hit is not None:
            hits.append(
                KnowledgeHit(
                    content=vector_hit.content,
                    source=vector_hit.source,
                    title_path=vector_hit.title_path,
                    similarity=hybrid_score,
                )
            )
            continue

        entry = entry_by_key.get(key)
        if entry is None:
            continue

        hits.append(
            KnowledgeHit(
                content=entry.content,
                source=entry.source,
                title_path=entry.title_path,
                similarity=hybrid_score,
            )
        )

    return sorted(hits, key=lambda hit: hit.similarity, reverse=True)[:top_k]


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize mixed Chinese/English project notes for BM25."""

    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _bm25_scores(query: str, entries: list[KnowledgeEntry]) -> list[float]:
    """Calculate raw BM25 scores, preferring rank_bm25 when installed."""

    tokenized_corpus = [tokenize_for_bm25(_entry_text(entry)) for entry in entries]
    query_tokens = tokenize_for_bm25(query)
    if not query_tokens:
        return [0.0 for _ in entries]

    if BM25Okapi is not None:
        bm25 = BM25Okapi(tokenized_corpus)
        scores = [float(score) for score in bm25.get_scores(query_tokens)]
        if any(score > 0 for score in scores):
            return scores

    return _fallback_bm25_scores(tokenized_corpus, query_tokens)


def _fallback_bm25_scores(
    tokenized_corpus: list[list[str]],
    query_tokens: list[str],
) -> list[float]:
    """Small BM25 implementation used only when rank_bm25 is unavailable."""

    if not tokenized_corpus:
        return []

    k1 = 1.5
    b = 0.75
    document_count = len(tokenized_corpus)
    document_lengths = [len(document) for document in tokenized_corpus]
    average_length = sum(document_lengths) / document_count if document_count else 0
    document_frequencies = Counter(
        token
        for document in tokenized_corpus
        for token in set(document)
    )

    scores = []
    for document, document_length in zip(tokenized_corpus, document_lengths):
        term_counts = Counter(document)
        score = 0.0
        for token in query_tokens:
            frequency = term_counts.get(token, 0)
            if frequency == 0:
                continue

            df = document_frequencies[token]
            idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (
                1 - b + b * document_length / max(average_length, 1)
            )
            score += idf * (frequency * (k1 + 1)) / denominator

        scores.append(score)

    return scores


def _normalize_scores(scores: list[float]) -> list[float]:
    """Normalize BM25 scores to 0-1 for fusion."""

    max_score = max(scores, default=0.0)
    if max_score <= 0:
        return [0.0 for _ in scores]

    return [score / max_score for score in scores]


def _top_bm25_keys(scores: dict[tuple[str, str, str], float], limit: int):
    """Return keys for the highest BM25 scores."""

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [key for key, _score in ranked[:limit]]


def _entry_text(entry: KnowledgeEntry) -> str:
    """Text used by BM25."""

    return f"{entry.title_path}\n{entry.content}"


def _hit_key(hit: KnowledgeHit) -> tuple[str, str, str]:
    """Stable key for a retrieval hit."""

    return (hit.source, hit.title_path, hit.content)


def _entry_key(entry: KnowledgeEntry) -> tuple[str, str, str]:
    """Stable key for a repository entry."""

    return (entry.source, entry.title_path, entry.content)


def _clamp_score(score: float) -> float:
    """Keep vector scores in the same 0-1 range as normalized BM25."""

    return max(0.0, min(float(score), 1.0))
