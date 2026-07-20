"""Tests for the provider-neutral reranker HTTP client."""

from __future__ import annotations

import json

import httpx
import pytest

from app.clients.reranker_client import (
    RerankCandidate,
    RerankerClient,
    RerankerError,
)
from app import config as config_module
from app.config import RerankerConfig


def _config() -> RerankerConfig:
    return RerankerConfig(
        provider="test-provider",
        api_key="secret-key",
        base_url="https://rerank.example.test/v1",
        model="test-reranker",
        timeout_seconds=5.0,
    )


def _candidates() -> list[RerankCandidate]:
    return [
        RerankCandidate(0, "A", "A\nfirst body", 0.9),
        RerankCandidate(1, "B", "B\nsecond body", 0.8),
    ]


def _client(handler) -> RerankerClient:
    transport = httpx.MockTransport(handler)
    return RerankerClient(_config(), http_client=httpx.Client(transport=transport))


def test_reranker_client_sends_one_batch_and_parses_all_scores():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://rerank.example.test/v1/rerank"
        assert request.headers["authorization"] == "Bearer secret-key"
        assert payload == {
            "model": "test-reranker",
            "query": "how to rank",
            "documents": ["A\nfirst body", "B\nsecond body"],
            "top_n": 2,
            "return_documents": False,
        }
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.25},
                ]
            },
        )

    with _client(handler) as client:
        scores = client.rerank(" how to rank ", _candidates(), top_n=1)

    assert len(requests) == 1
    assert [(score.index, score.score) for score in scores] == [(1, 0.95), (0, 0.25)]


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (429, "rerank_rate_limited"),
        (401, "rerank_auth_failed"),
        (403, "rerank_auth_failed"),
        (500, "rerank_provider_error"),
        (400, "rerank_provider_error"),
    ],
)
def test_reranker_client_maps_http_errors(status_code: int, expected_code: str):
    client = _client(lambda request: httpx.Response(status_code, json={"error": "private"}))

    with pytest.raises(RerankerError) as captured:
        client.rerank("query", _candidates(), top_n=2)

    assert captured.value.code == expected_code
    client.close()


def test_reranker_client_maps_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with pytest.raises(RerankerError) as captured:
        client.rerank("query", _candidates(), top_n=2)

    assert captured.value.code == "rerank_timeout"
    client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"results": "bad"},
        {"results": [{"index": 0, "relevance_score": 0.1}]},
        {
            "results": [
                {"index": 0, "relevance_score": 0.1},
                {"index": 0, "relevance_score": 0.2},
            ]
        },
        {
            "results": [
                {"index": 0, "relevance_score": 0.1},
                {"index": 3, "relevance_score": 0.2},
            ]
        },
        {
            "results": [
                {"index": 0, "relevance_score": float("nan")},
                {"index": 1, "relevance_score": 0.2},
            ]
        },
        {
            "results": [
                {"index": 0, "relevance_score": float("inf")},
                {"index": 1, "relevance_score": 0.2},
            ]
        },
        {
            "results": [
                {"index": 0, "relevance_score": "0.1"},
                {"index": 1, "relevance_score": 0.2},
            ]
        },
    ],
)
def test_reranker_client_rejects_invalid_responses(payload):
    client = _client(
        lambda request: httpx.Response(
            200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
    )

    with pytest.raises(RerankerError) as captured:
        client.rerank("query", _candidates(), top_n=2)

    assert captured.value.code == "rerank_invalid_response"
    client.close()


def test_reranker_error_does_not_expose_response_or_documents():
    secret_body = "private chunk body"
    candidates = [RerankCandidate(0, "title", secret_body, 0.9)]
    client = _client(
        lambda request: httpx.Response(500, text="provider leaked secret-key and private body")
    )

    with pytest.raises(RerankerError) as captured:
        client.rerank("query", candidates, top_n=1)

    message = str(captured.value)
    assert "secret-key" not in message
    assert secret_body not in message
    assert "provider leaked" not in message
    client.close()


def test_load_reranker_config_reads_independent_environment(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("RERANK_PROVIDER", "Compatible")
    monkeypatch.setenv("RERANK_API_KEY", "rerank-only-key")
    monkeypatch.setenv("RERANK_BASE_URL", "https://example.test/v2/")
    monkeypatch.setenv("RERANK_MODEL", "rerank-model")
    monkeypatch.setenv("RERANK_TIMEOUT_SECONDS", "4.5")

    config = config_module.load_reranker_config()

    assert config == RerankerConfig(
        provider="compatible",
        api_key="rerank-only-key",
        base_url="https://example.test/v2",
        model="rerank-model",
        timeout_seconds=4.5,
    )


def test_load_reranker_config_rejects_missing_configuration(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    for name in (
        "RERANK_PROVIDER",
        "RERANK_API_KEY",
        "RERANK_BASE_URL",
        "RERANK_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RERANK_TIMEOUT_SECONDS", "5")

    with pytest.raises(RuntimeError, match="provider"):
        config_module.load_reranker_config()


@pytest.mark.parametrize(
    "candidates",
    [
        [RerankCandidate(1, "A", "body", 0.9)],
        [
            RerankCandidate(0, "A", "body", 0.9),
            RerankCandidate(0, "B", "body", 0.8),
        ],
    ],
)
def test_reranker_client_rejects_invalid_candidate_indices(candidates):
    client = _client(
        lambda request: (_ for _ in ()).throw(AssertionError("must fail before HTTP"))
    )

    with pytest.raises(RerankerError) as captured:
        client.rerank("query", candidates, top_n=len(candidates))

    assert captured.value.code == "rerank_invalid_response"
    client.close()
