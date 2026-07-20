from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

import app.clients.web_search_client as client_module
import app.config as config_module
from app.clients.web_search_client import (
    TavilyWebSearchProvider,
    WebSearchClient,
    WebSearchError,
    close_web_search_client,
    get_web_search_client,
)
from app.config import WebSearchConfig, load_web_search_config


class FixedClock:
    def today_utc(self) -> date:
        return date(2026, 7, 20)


def make_config(**overrides) -> WebSearchConfig:
    values = {
        "provider": "tavily",
        "api_key": "tvly-test-key",
        "base_url": "https://api.tavily.test",
        "timeout_seconds": 7.0,
    }
    values.update(overrides)
    return WebSearchConfig(**values)


def make_client(handler, *, clock=None) -> WebSearchClient:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_config(), clock=clock or FixedClock())
    return WebSearchClient(provider, http_client=http_client)


def test_load_web_search_config_prefers_generic_api_key(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "generic-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "6.5")

    config = load_web_search_config()

    assert config == WebSearchConfig(
        provider="tavily",
        api_key="generic-key",
        base_url="https://api.tavily.com",
        timeout_seconds=6.5,
    )


def test_load_web_search_config_accepts_tavily_key(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-key")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "invalid")

    config = load_web_search_config()

    assert config.api_key == "tavily-key"
    assert config.timeout_seconds == 7.0


def test_load_web_search_config_missing_key_fails_only_when_loaded(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="not configured"):
        load_web_search_config()


def test_tavily_request_maps_freshness_and_fixed_options():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"results": []})

    with make_client(handler) as client:
        response = client.search("latest FastAPI changes", 5, 7)

    request = captured["request"]
    body = json.loads(request.content)
    assert request.url == "https://api.tavily.test/search"
    assert request.headers["Authorization"] == "Bearer tvly-test-key"
    assert body == {
        "query": "latest FastAPI changes",
        "max_results": 5,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "auto_parameters": False,
        "start_date": "2026-07-13",
    }
    assert "freshness_days" not in body
    assert response.provider == "tavily"
    assert response.cached is False


def test_tavily_request_omits_start_date_without_freshness():
    captured_body = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    with make_client(handler) as client:
        client.search("FastAPI documentation", 3)

    assert "start_date" not in captured_body
    assert "freshness_days" not in captured_body


def test_results_are_filtered_normalized_truncated_and_deduplicated():
    long_snippet = "x" * 900

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "  Release Notes  ",
                        "url": "HTTPS://Example.COM:443/Path/Case?B=2&A=1#section",
                        "content": long_snippet,
                        "published_date": "2026-07-19",
                    },
                    {
                        "title": "duplicate",
                        "url": "https://example.com/Path/Case?B=2&A=1#other",
                        "content": "duplicate content",
                    },
                    {"title": "insecure", "url": "http://example.com/a"},
                    {"title": "userinfo", "url": "https://user:pass@example.com/a"},
                    {"title": "", "url": "https://example.com/no-title"},
                    {"title": "missing url"},
                ]
            },
        )

    with make_client(handler) as client:
        response = client.search("release notes")

    assert len(response.items) == 1
    item = response.items[0]
    assert item.title == "Release Notes"
    assert item.url == "https://example.com/Path/Case?B=2&A=1"
    assert item.domain == "example.com"
    assert len(item.snippet) == 800
    assert item.published_at == "2026-07-19"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(401, "provider_auth_failed"), (403, "provider_auth_failed"), (429, "rate_limited"), (500, "provider_error")],
)
def test_http_errors_are_mapped(status_code, expected_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="secret provider response")

    with make_client(handler) as client:
        with pytest.raises(WebSearchError) as captured:
            client.search("query")

    assert captured.value.code == expected_code
    assert "secret provider response" not in captured.value.message
    assert "tvly-test-key" not in captured.value.message


def test_timeout_is_mapped_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timed out with tvly-test-key", request=request)

    with make_client(handler) as client:
        with pytest.raises(WebSearchError) as captured:
            client.search("query")

    assert captured.value.code == "search_timeout"
    assert captured.value.message == "web search timed out"
    assert calls == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"unexpected": []}),
        httpx.Response(200, json={"results": {}}),
        httpx.Response(200, json={"results": ["invalid item"]}),
    ],
)
def test_invalid_provider_responses_are_mapped(response):
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with make_client(handler) as client:
        with pytest.raises(WebSearchError) as captured:
            client.search("query")

    assert captured.value.code == "provider_error"


def test_repeated_searches_reuse_one_injected_http_client():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    client = make_client(handler)
    injected_http_client = client._http_client
    with client:
        client.search("first query")
        client.search("second query")
        assert client._http_client is injected_http_client

    assert len(calls) == 2
    assert injected_http_client.is_closed


def test_get_client_is_lazy_maps_missing_config_and_can_be_closed(monkeypatch):
    close_web_search_client()

    def missing_config():
        raise RuntimeError("missing key tvly-never-expose")

    monkeypatch.setattr(client_module, "load_web_search_config", missing_config)
    with pytest.raises(WebSearchError) as captured:
        get_web_search_client()
    assert captured.value.code == "search_not_configured"
    assert "tvly-never-expose" not in captured.value.message

    monkeypatch.setattr(client_module, "load_web_search_config", make_config)
    first = get_web_search_client()
    second = get_web_search_client()
    assert first is second

    close_web_search_client()
    assert first.is_closed
