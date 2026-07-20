"""Provider-neutral HTTP client for batch document reranking."""

from __future__ import annotations

from dataclasses import dataclass
import math
from threading import Lock
from typing import Any

import httpx

from app.config import RerankerConfig, load_reranker_config


@dataclass(frozen=True)
class RerankCandidate:
    """A retrieval hit converted into a provider-safe rerank candidate."""

    index: int
    title_path: str
    text: str
    retrieval_score: float


@dataclass(frozen=True)
class RerankScore:
    """Provider score mapped back to the immutable candidate index."""

    index: int
    score: float


class RerankerError(Exception):
    """Sanitized reranker failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str = "reranker request failed") -> None:
        self.code = code
        super().__init__(message)


class RerankerClient:
    """Call a Cohere-compatible rerank endpoint in one batch request."""

    def __init__(
        self,
        config: RerankerConfig,
        *,
        http_client: httpx.Client,
    ) -> None:
        self.config = config
        self._http_client = http_client
        self._closed = False

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def is_closed(self) -> bool:
        return self._closed or self._http_client.is_closed

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        *,
        top_n: int,
    ) -> list[RerankScore]:
        """Score all candidates with one provider request."""

        normalized_query = query.strip() if isinstance(query, str) else ""
        if not normalized_query:
            raise RerankerError("rerank_invalid_response", "invalid rerank query")
        if not candidates:
            return []
        _validate_candidates(candidates)
        if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
            raise RerankerError("rerank_invalid_response", "invalid rerank top_n")
        if self.is_closed:
            raise RerankerError("rerank_provider_error", "reranker client is closed")

        payload = {
            "model": self.config.model,
            "query": normalized_query,
            "documents": [candidate.text for candidate in candidates],
            # The service performs the final stable Top-N selection. Asking the
            # provider for every score prevents missing-index ambiguity.
            "top_n": len(candidates),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._http_client.post(
                _rerank_endpoint(self.config.base_url),
                headers=headers,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise RerankerError("rerank_timeout", "reranker request timed out") from exc
        except httpx.HTTPError as exc:
            raise RerankerError("rerank_provider_error") from exc

        if response.status_code == 429:
            raise RerankerError("rerank_rate_limited", "reranker rate limited")
        if response.status_code in {401, 403}:
            raise RerankerError("rerank_auth_failed", "reranker authentication failed")
        if response.status_code >= 500:
            raise RerankerError("rerank_provider_error")
        if response.status_code >= 400:
            raise RerankerError("rerank_provider_error")

        try:
            body = response.json()
        except ValueError as exc:
            raise RerankerError("rerank_invalid_response") from exc

        return _parse_scores(body, candidates)

    def close(self) -> None:
        if not self._closed:
            self._http_client.close()
            self._closed = True

    def __enter__(self) -> RerankerClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def _validate_candidates(candidates: list[RerankCandidate]) -> None:
    expected = set(range(len(candidates)))
    indices: set[int] = set()
    for candidate in candidates:
        index = getattr(candidate, "index", None)
        if isinstance(index, bool) or not isinstance(index, int):
            raise RerankerError("rerank_invalid_response")
        if index not in expected or index in indices:
            raise RerankerError("rerank_invalid_response")
        if not isinstance(getattr(candidate, "text", None), str):
            raise RerankerError("rerank_invalid_response")
        indices.add(index)
    if indices != expected:
        raise RerankerError("rerank_invalid_response")


def _parse_scores(
    body: Any,
    candidates: list[RerankCandidate],
) -> list[RerankScore]:
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        raise RerankerError("rerank_invalid_response")

    expected_indices = {candidate.index for candidate in candidates}
    scores: list[RerankScore] = []
    seen: set[int] = set()
    for item in body["results"]:
        if not isinstance(item, dict):
            raise RerankerError("rerank_invalid_response")
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if isinstance(index, bool) or not isinstance(index, int):
            raise RerankerError("rerank_invalid_response")
        if index not in expected_indices or index in seen:
            raise RerankerError("rerank_invalid_response")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RerankerError("rerank_invalid_response")
        normalized_score = float(score)
        if not math.isfinite(normalized_score):
            raise RerankerError("rerank_invalid_response")
        seen.add(index)
        scores.append(RerankScore(index=index, score=normalized_score))

    if seen != expected_indices:
        raise RerankerError("rerank_invalid_response")
    return scores


def _rerank_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/rerank"):
        return normalized
    return f"{normalized}/rerank"


_client_lock = Lock()
_reranker_client: RerankerClient | None = None


def get_reranker_client() -> RerankerClient:
    """Lazily load configuration and create the shared reranker client."""

    global _reranker_client
    if _reranker_client is not None and not _reranker_client.is_closed:
        return _reranker_client

    with _client_lock:
        if _reranker_client is not None and not _reranker_client.is_closed:
            return _reranker_client
        try:
            config = load_reranker_config()
        except RuntimeError as exc:
            raise RerankerError(
                "rerank_not_configured",
                "reranker is not configured",
            ) from exc
        _reranker_client = RerankerClient(
            config,
            http_client=httpx.Client(timeout=config.timeout_seconds),
        )
        return _reranker_client


def close_reranker_client() -> None:
    """Close and clear the shared reranker client."""

    global _reranker_client
    with _client_lock:
        client = _reranker_client
        _reranker_client = None
    if client is not None:
        client.close()
