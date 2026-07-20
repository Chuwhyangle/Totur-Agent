"""Stable reranking orchestration with lossless fallback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import math
import time
from typing import Protocol

from app.clients.reranker_client import (
    RerankCandidate,
    RerankerError,
    RerankScore,
    get_reranker_client,
)
from app.repositories.knowledge_repository import KnowledgeHit
from app.services.rag_settings import (
    ENABLE_RERANKING,
    RERANK_CANDIDATE_K,
    RERANK_MAX_TEXT_CHARS,
)


logger = logging.getLogger(__name__)


class RerankerClientProtocol(Protocol):
    provider: str
    model: str

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        *,
        top_n: int,
    ) -> list[RerankScore]: ...


@dataclass(frozen=True)
class RerankOutcome:
    hits: list[KnowledgeHit]
    scores_by_index: dict[int, float]
    applied: bool
    latency_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    fallback_reason: str | None = None


class RerankingService:
    """Build candidates, call a client once, and preserve retrieval data."""

    def __init__(
        self,
        *,
        enabled: bool = ENABLE_RERANKING,
        client_factory: Callable[[], RerankerClientProtocol] = get_reranker_client,
        candidate_k: int = RERANK_CANDIDATE_K,
        max_text_chars: int = RERANK_MAX_TEXT_CHARS,
    ) -> None:
        self.enabled = enabled
        self._client_factory = client_factory
        self.candidate_k = max(1, int(candidate_k))
        self.max_text_chars = max(0, int(max_text_chars))
        self._client: RerankerClientProtocol | None = None

    def rerank(
        self,
        query: str,
        hits: list[KnowledgeHit],
        *,
        top_n: int,
    ) -> RerankOutcome:
        candidate_hits = list(hits[: self.candidate_k])
        safe_top_n = max(0, min(int(top_n), len(candidate_hits)))

        if not self.enabled or not candidate_hits or safe_top_n <= 0:
            return RerankOutcome(
                hits=candidate_hits[:safe_top_n],
                scores_by_index={},
                applied=False,
            )
        if len(candidate_hits) == 1:
            return RerankOutcome(
                hits=candidate_hits[:safe_top_n],
                scores_by_index={},
                applied=False,
            )

        candidates = [
            RerankCandidate(
                index=index,
                title_path=hit.title_path,
                text=_candidate_text(hit, self.max_text_chars),
                retrieval_score=hit.similarity,
            )
            for index, hit in enumerate(candidate_hits)
        ]

        started = time.perf_counter()
        try:
            client = self._get_client()
            scores = client.rerank(
                query,
                candidates,
                top_n=len(candidates),
            )
            scores_by_index = _validated_scores(scores, len(candidates))
        except RerankerError as exc:
            latency_ms = _elapsed_ms(started)
            logger.warning("reranker fallback: %s", exc.code)
            return RerankOutcome(
                hits=candidate_hits[:safe_top_n],
                scores_by_index={},
                applied=False,
                latency_ms=latency_ms,
                fallback_reason=exc.code,
            )
        except Exception as exc:  # pragma: no cover - final service boundary guard.
            latency_ms = _elapsed_ms(started)
            logger.warning("reranker fallback: rerank_provider_error (%s)", type(exc).__name__)
            return RerankOutcome(
                hits=candidate_hits[:safe_top_n],
                scores_by_index={},
                applied=False,
                latency_ms=latency_ms,
                fallback_reason="rerank_provider_error",
            )

        ordered_indices = sorted(
            range(len(candidate_hits)),
            key=lambda index: (
                -scores_by_index[index],
                -candidate_hits[index].similarity,
                index,
            ),
        )
        latency_ms = _elapsed_ms(started)
        return RerankOutcome(
            hits=[candidate_hits[index] for index in ordered_indices[:safe_top_n]],
            scores_by_index=scores_by_index,
            applied=True,
            latency_ms=latency_ms,
            provider=str(getattr(client, "provider", "") or "") or None,
            model=str(getattr(client, "model", "") or "") or None,
        )

    def _get_client(self) -> RerankerClientProtocol:
        if self._client is None:
            self._client = self._client_factory()
        return self._client


def _candidate_text(hit: KnowledgeHit, max_text_chars: int) -> str:
    title = hit.title_path.strip()
    if not title:
        # Never send an absolute source path to an external provider.
        title = hit.source.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    content = hit.content[:max_text_chars] if max_text_chars else ""
    return f"{title}\n{content}"


def _validated_scores(
    scores: list[RerankScore],
    candidate_count: int,
) -> dict[int, float]:
    if not isinstance(scores, list):
        raise RerankerError("rerank_invalid_response")

    result: dict[int, float] = {}
    for item in scores:
        index = getattr(item, "index", None)
        score = getattr(item, "score", None)
        if isinstance(index, bool) or not isinstance(index, int):
            raise RerankerError("rerank_invalid_response")
        if index < 0 or index >= candidate_count or index in result:
            raise RerankerError("rerank_invalid_response")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RerankerError("rerank_invalid_response")
        normalized_score = float(score)
        if not math.isfinite(normalized_score):
            raise RerankerError("rerank_invalid_response")
        result[index] = normalized_score

    if set(result) != set(range(candidate_count)):
        raise RerankerError("rerank_invalid_response")
    return result


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
