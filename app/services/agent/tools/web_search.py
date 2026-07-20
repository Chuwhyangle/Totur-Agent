"""Public web search tool with validation and stable result contracts."""

from __future__ import annotations

import re
from typing import Any


_MAX_QUERY_CHARS = 300
_MIN_RESULTS = 1
_MAX_RESULTS = 5
_MIN_FRESHNESS_DAYS = 1
_MAX_FRESHNESS_DAYS = 3650

_SENSITIVE_QUERY_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}", re.IGNORECASE),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"\bxoxb-[A-Za-z0-9-]{8,}", re.IGNORECASE),
    re.compile(r"\btvly-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(
        r"\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"
    ),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|token|password|passwd|pwd)"
        r"\s*[:=]\s*[\"']?[^\s\"'&;]{4,}",
        re.IGNORECASE,
    ),
)


def get_web_search_client() -> Any:
    """Resolve the shared client lazily so importing tools never loads configuration."""

    from app.clients.web_search_client import get_web_search_client as get_client

    return get_client()


def web_search(
    query: str,
    max_results: int = 5,
    freshness_days: int | None = None,
) -> dict[str, Any]:
    """Search public web sources and return a provider-independent result."""

    validation_error = _validate_arguments(query, max_results, freshness_days)
    if validation_error is not None:
        return validation_error

    normalized_query = query.strip()
    normalized_max_results = _clamp(max_results, _MIN_RESULTS, _MAX_RESULTS)
    normalized_freshness_days = (
        None
        if freshness_days is None
        else _clamp(
            freshness_days,
            _MIN_FRESHNESS_DAYS,
            _MAX_FRESHNESS_DAYS,
        )
    )

    if _contains_sensitive_credential(normalized_query):
        return {
            "ok": False,
            "error": "sensitive_query_rejected",
            "message": "query appears to contain a sensitive credential",
        }

    try:
        response = get_web_search_client().search(
            normalized_query,
            normalized_max_results,
            normalized_freshness_days,
        )
        return _build_success_result(normalized_query, response)
    except Exception as exc:  # Client errors and a final provider safety boundary.
        mapped_error = _map_client_error(exc)
        if mapped_error is not None:
            return mapped_error
        return {
            "ok": False,
            "error": "provider_error",
            "message": "web search provider failed",
        }


def _validate_arguments(
    query: Any,
    max_results: Any,
    freshness_days: Any,
) -> dict[str, Any] | None:
    if not isinstance(query, str) or not query.strip():
        return _invalid_arguments("query must be a non-empty string.")
    if len(query.strip()) > _MAX_QUERY_CHARS:
        return _invalid_arguments("query must be at most 300 characters.")
    if not _is_integer(max_results):
        return _invalid_arguments("max_results must be an integer.")
    if freshness_days is not None and not _is_integer(freshness_days):
        return _invalid_arguments("freshness_days must be an integer when provided.")
    return None


def _contains_sensitive_credential(query: str) -> bool:
    return any(pattern.search(query) for pattern in _SENSITIVE_QUERY_PATTERNS)


def _build_success_result(query: str, response: Any) -> dict[str, Any]:
    items = [_serialize_item(item) for item in response.items]
    return {
        "ok": True,
        "found": bool(items),
        "query": query,
        "items": items,
        "summary": {
            "returned_count": len(items),
            "provider": response.provider,
            "provider_latency_ms": response.provider_latency_ms,
            "cached": response.cached,
        },
    }


def _serialize_item(item: Any) -> dict[str, Any]:
    return {
        "title": item.title,
        "url": item.url,
        "snippet": item.snippet,
        "domain": item.domain,
        "published_at": item.published_at,
    }


def _map_client_error(exc: Exception) -> dict[str, Any] | None:
    try:
        from app.clients.web_search_client import WebSearchError
    except ImportError:  # pragma: no cover - only possible during an incomplete deploy.
        return None

    if not isinstance(exc, WebSearchError):
        return None
    return {
        "ok": False,
        "error": exc.code,
        "message": exc.message,
    }


def _invalid_arguments(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "invalid_arguments",
        "message": message,
    }


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
