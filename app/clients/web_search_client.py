"""Provider-independent web search client with a Tavily adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config import WebSearchConfig, load_web_search_config
from app.services.web_search_settings import (
    WEB_SEARCH_MAX_FRESHNESS_DAYS,
    WEB_SEARCH_MAX_QUERY_CHARS,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_MAX_SNIPPET_CHARS,
)


@dataclass(frozen=True)
class WebSearchItem:
    """A normalized, safe web search result."""

    title: str
    url: str
    snippet: str
    domain: str
    published_at: str | None = None


@dataclass(frozen=True)
class WebSearchResponse:
    """Provider-independent search response."""

    items: list[WebSearchItem]
    provider: str
    provider_latency_ms: int
    cached: bool = False


class WebSearchError(Exception):
    """Stable web search failure exposed to the tool layer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class WebSearchClock(Protocol):
    """Injectable UTC calendar used for deterministic freshness mapping."""

    def today_utc(self) -> date:
        ...


class SystemWebSearchClock:
    """Production UTC calendar."""

    def today_utc(self) -> date:
        return datetime.now(timezone.utc).date()


class WebSearchProvider(Protocol):
    """Provider adapter contract consumed by WebSearchClient."""

    name: str

    def search(
        self,
        *,
        http_client: httpx.Client,
        query: str,
        max_results: int,
        freshness_days: int | None,
    ) -> WebSearchResponse:
        ...


def _normalize_https_url(raw_url: str) -> tuple[str, str] | None:
    candidate = raw_url.strip()
    if not candidate or "\\" in candidate or any(ord(char) < 32 for char in candidate):
        return None

    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return None
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            return None

        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError:
        return None

    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port in (None, 443) else f"{rendered_host}:{port}"
    normalized = urlunsplit(("https", netloc, parsed.path, parsed.query, ""))
    return normalized, host


def _normalize_results(results: list[Any]) -> list[WebSearchItem]:
    items: list[WebSearchItem] = []
    seen_urls: set[str] = set()

    for result in results:
        if not isinstance(result, dict):
            raise WebSearchError("provider_error", "web search provider returned an invalid response")

        raw_title = result.get("title")
        raw_url = result.get("url")
        if not isinstance(raw_title, str) or not isinstance(raw_url, str):
            continue

        title = raw_title.strip()
        normalized_url = _normalize_https_url(raw_url)
        if not title or normalized_url is None:
            continue

        url, domain = normalized_url
        if url in seen_urls:
            continue

        seen_urls.add(url)

        raw_snippet = result.get("content", result.get("snippet", ""))
        snippet = raw_snippet if isinstance(raw_snippet, str) else ""
        snippet = snippet[:WEB_SEARCH_MAX_SNIPPET_CHARS]

        raw_published_at = result.get("published_date", result.get("published_at"))
        published_at = raw_published_at if isinstance(raw_published_at, str) else None

        items.append(
            WebSearchItem(
                title=title,
                url=url,
                snippet=snippet,
                domain=domain,
                published_at=published_at,
            )
        )

    return items


class TavilyWebSearchProvider:
    """Translate the stable search contract to Tavily's HTTP API."""

    name = "tavily"

    def __init__(
        self,
        config: WebSearchConfig,
        *,
        clock: WebSearchClock | Callable[[], date] | None = None,
        monotonic: Callable[[], float] = perf_counter,
    ) -> None:
        self._config = config
        self._clock = clock or SystemWebSearchClock()
        self._monotonic = monotonic

    def _today_utc(self) -> date:
        if callable(self._clock):
            return self._clock()
        return self._clock.today_utc()

    def _search_url(self) -> str:
        base_url = self._config.base_url.rstrip("/")
        return base_url if base_url.endswith("/search") else f"{base_url}/search"

    def search(
        self,
        *,
        http_client: httpx.Client,
        query: str,
        max_results: int,
        freshness_days: int | None,
    ) -> WebSearchResponse:
        request_body: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "auto_parameters": False,
        }
        if freshness_days is not None:
            start_date = self._today_utc() - timedelta(days=freshness_days)
            request_body["start_date"] = start_date.isoformat()

        started_at = self._monotonic()
        try:
            response = http_client.post(
                self._search_url(),
                headers={"Authorization": f"Bearer {self._config.api_key}"},
                json=request_body,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise WebSearchError("search_timeout", "web search timed out") from exc
        except httpx.RequestError as exc:
            raise WebSearchError("provider_error", "web search provider request failed") from exc
        provider_latency_ms = max(0, int((self._monotonic() - started_at) * 1000))

        if response.status_code in (401, 403):
            raise WebSearchError(
                "provider_auth_failed",
                "web search provider authentication failed",
            )
        if response.status_code == 429:
            raise WebSearchError("rate_limited", "web search provider rate limited the request")
        if response.is_error:
            raise WebSearchError("provider_error", "web search provider returned an error")

        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise WebSearchError(
                "provider_error",
                "web search provider returned an invalid response",
            ) from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise WebSearchError(
                "provider_error",
                "web search provider returned an invalid response",
            )

        return WebSearchResponse(
            items=_normalize_results(payload["results"]),
            provider=self.name,
            provider_latency_ms=provider_latency_ms,
            cached=False,
        )


class WebSearchClient:
    """Reusable synchronous web search entry point."""

    def __init__(
        self,
        provider: WebSearchProvider,
        *,
        http_client: httpx.Client,
    ) -> None:
        self._provider = provider
        self._http_client = http_client
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed or self._http_client.is_closed

    def search(
        self,
        query: str,
        max_results: int = WEB_SEARCH_MAX_RESULTS,
        freshness_days: int | None = None,
    ) -> WebSearchResponse:
        normalized_query = query.strip() if isinstance(query, str) else ""
        if not normalized_query or len(normalized_query) > WEB_SEARCH_MAX_QUERY_CHARS:
            raise WebSearchError("invalid_arguments", "invalid web search query")
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= WEB_SEARCH_MAX_RESULTS
        ):
            raise WebSearchError("invalid_arguments", "invalid max_results")
        if freshness_days is not None and (
            isinstance(freshness_days, bool)
            or not isinstance(freshness_days, int)
            or not 1 <= freshness_days <= WEB_SEARCH_MAX_FRESHNESS_DAYS
        ):
            raise WebSearchError("invalid_arguments", "invalid freshness_days")
        if self.is_closed:
            raise WebSearchError("provider_error", "web search client is closed")

        return self._provider.search(
            http_client=self._http_client,
            query=normalized_query,
            max_results=max_results,
            freshness_days=freshness_days,
        )

    def close(self) -> None:
        if not self._closed:
            self._http_client.close()
            self._closed = True

    def __enter__(self) -> WebSearchClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


_client_lock = Lock()
_web_search_client: WebSearchClient | None = None


def get_web_search_client() -> WebSearchClient:
    """Lazily create and reuse the application-level web search client."""

    global _web_search_client
    if _web_search_client is not None and not _web_search_client.is_closed:
        return _web_search_client

    with _client_lock:
        if _web_search_client is not None and not _web_search_client.is_closed:
            return _web_search_client
        try:
            config = load_web_search_config()
        except RuntimeError as exc:
            raise WebSearchError(
                "search_not_configured",
                "web search is not configured",
            ) from exc

        http_client = httpx.Client(timeout=config.timeout_seconds)
        provider = TavilyWebSearchProvider(config)
        _web_search_client = WebSearchClient(provider, http_client=http_client)
        return _web_search_client


def close_web_search_client() -> None:
    """Close and clear the lazily-created application client."""

    global _web_search_client
    with _client_lock:
        client = _web_search_client
        _web_search_client = None
    if client is not None:
        client.close()

