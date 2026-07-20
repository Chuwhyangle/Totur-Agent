"""Tests for the public web search Agent tool."""

from __future__ import annotations

import pytest

from app.clients.web_search_client import (
    WebSearchError,
    WebSearchItem,
    WebSearchResponse,
)
import app.services.agent.tools.web_search as web_search_module


class FakeWebSearchClient:
    def __init__(
        self,
        response: WebSearchResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or WebSearchResponse(
            items=[],
            provider="tavily",
            provider_latency_ms=0,
        )
        self.error = error
        self.calls: list[tuple[str, int, int | None]] = []

    def search(
        self,
        query: str,
        max_results: int,
        freshness_days: int | None,
    ) -> WebSearchResponse:
        self.calls.append((query, max_results, freshness_days))
        if self.error is not None:
            raise self.error
        return self.response


def install_fake_client(monkeypatch, client: FakeWebSearchClient) -> None:
    monkeypatch.setattr(web_search_module, "get_web_search_client", lambda: client)


@pytest.mark.parametrize("query", ["", "   ", None, 123])
def test_web_search_rejects_empty_or_non_string_query(monkeypatch, query):
    client = FakeWebSearchClient()
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search(query)  # type: ignore[arg-type]

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "query must be a non-empty string.",
    }
    assert client.calls == []


def test_web_search_rejects_query_over_300_characters(monkeypatch):
    client = FakeWebSearchClient()
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("x" * 301)

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "query must be at most 300 characters.",
    }
    assert client.calls == []


@pytest.mark.parametrize(
    ("max_results", "freshness_days", "expected_max", "expected_freshness"),
    [
        (-10, -20, 1, 1),
        (1, None, 1, None),
        (99, 9999, 5, 3650),
    ],
)
def test_web_search_normalizes_numeric_boundaries(
    monkeypatch,
    max_results,
    freshness_days,
    expected_max,
    expected_freshness,
):
    client = FakeWebSearchClient()
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search(
        "  latest FastAPI changes  ",
        max_results=max_results,
        freshness_days=freshness_days,
    )

    assert result["ok"] is True
    assert result["query"] == "latest FastAPI changes"
    assert client.calls == [
        ("latest FastAPI changes", expected_max, expected_freshness)
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_results": 2.5}, "max_results must be an integer."),
        ({"max_results": True}, "max_results must be an integer."),
        (
            {"freshness_days": "7"},
            "freshness_days must be an integer when provided.",
        ),
        (
            {"freshness_days": False},
            "freshness_days must be an integer when provided.",
        ),
    ],
)
def test_web_search_rejects_non_integer_numeric_arguments(monkeypatch, kwargs, message):
    client = FakeWebSearchClient()
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("FastAPI", **kwargs)

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": message,
    }
    assert client.calls == []


@pytest.mark.parametrize(
    "query",
    [
        "debug sk-abcdefghijklmnop",
        "find ghp_abcdefghijklmnopqrstuvwxyz",
        "inspect github_pat_abcdefghijklmnopqrstuvwxyz_123456",
        "lookup xoxb-1234567890-secret",
        "search tvly-abcdefghijklmnopqrstuvwxyz123456",
        "Authorization: Bearer abcdefghijklmnop",
        "decode eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
        "api_key=super-secret-value",
        "token: private-token-value",
        "password=hunter2",
    ],
)
def test_web_search_rejects_sensitive_credentials_without_calling_client(
    monkeypatch,
    query,
):
    client = FakeWebSearchClient()
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search(query)

    assert result == {
        "ok": False,
        "error": "sensitive_query_rejected",
        "message": "query appears to contain a sensitive credential",
    }
    assert client.calls == []


def test_web_search_returns_stable_success_structure(monkeypatch):
    client = FakeWebSearchClient(
        WebSearchResponse(
            items=[
                WebSearchItem(
                    title="FastAPI Release Notes",
                    url="https://fastapi.tiangolo.com/release-notes/",
                    snippet="Recent changes.",
                    domain="fastapi.tiangolo.com",
                    published_at="2026-07-18",
                )
            ],
            provider="tavily",
            provider_latency_ms=820,
            cached=False,
        )
    )
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("latest FastAPI changes")

    assert result == {
        "ok": True,
        "found": True,
        "query": "latest FastAPI changes",
        "items": [
            {
                "title": "FastAPI Release Notes",
                "url": "https://fastapi.tiangolo.com/release-notes/",
                "snippet": "Recent changes.",
                "domain": "fastapi.tiangolo.com",
                "published_at": "2026-07-18",
            }
        ],
        "summary": {
            "returned_count": 1,
            "provider": "tavily",
            "provider_latency_ms": 820,
            "cached": False,
        },
    }
    assert "evidence_id" not in result["items"][0]


def test_web_search_treats_empty_results_as_success(monkeypatch):
    client = FakeWebSearchClient(
        WebSearchResponse(
            items=[],
            provider="tavily",
            provider_latency_ms=430,
            cached=False,
        )
    )
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("uncommon query")

    assert result == {
        "ok": True,
        "found": False,
        "query": "uncommon query",
        "items": [],
        "summary": {
            "returned_count": 0,
            "provider": "tavily",
            "provider_latency_ms": 430,
            "cached": False,
        },
    }


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("search_not_configured", "web search is not configured"),
        ("search_timeout", "web search timed out"),
        ("rate_limited", "web search rate limit exceeded"),
        ("provider_auth_failed", "web search provider authentication failed"),
        ("provider_error", "web search provider failed"),
    ],
)
def test_web_search_maps_client_errors(monkeypatch, code, message):
    client = FakeWebSearchClient(error=WebSearchError(code, message))
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("latest FastAPI changes")

    assert result == {"ok": False, "error": code, "message": message}


def test_web_search_hides_unexpected_exception_details(monkeypatch):
    client = FakeWebSearchClient(error=RuntimeError("api_key=must-not-leak"))
    install_fake_client(monkeypatch, client)

    result = web_search_module.web_search("latest FastAPI changes")

    assert result == {
        "ok": False,
        "error": "provider_error",
        "message": "web search provider failed",
    }
    assert "must-not-leak" not in str(result)
