"""Embedding 客户端和配置的单元测试。"""

from types import SimpleNamespace

import pytest

import app.config as config_module
from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import EmbeddingConfig, load_embedding_config


def test_load_embedding_config_reads_openai_compatible_environment(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-demo")

    config = load_embedding_config()

    assert config == EmbeddingConfig(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="text-embedding-demo",
    )


def test_load_embedding_config_requires_embedding_model(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="embedding model"):
        load_embedding_config()


class FakeEmbeddingApi:
    """记录 embedding 请求并返回固定向量。"""

    def __init__(self) -> None:
        self.calls = []

    def create(self, model: str, input: list[str]):
        self.calls.append({"model": model, "input": input})
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[1.0, 0.0]),
                SimpleNamespace(embedding=[0.0, 1.0]),
            ]
        )


def test_embedding_client_embeds_texts_with_configured_model():
    embeddings_api = FakeEmbeddingApi()
    fake_client = SimpleNamespace(embeddings=embeddings_api)
    client = EmbeddingClient(
        config=EmbeddingConfig(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="text-embedding-demo",
        ),
        client=fake_client,
    )

    embeddings = client.embed_texts(["第一段", "第二段"])

    assert embeddings == [[1.0, 0.0], [0.0, 1.0]]
    assert embeddings_api.calls == [
        {
            "model": "text-embedding-demo",
            "input": ["第一段", "第二段"],
        }
    ]


def test_embedding_client_returns_empty_list_without_api_call():
    embeddings_api = FakeEmbeddingApi()
    fake_client = SimpleNamespace(embeddings=embeddings_api)
    client = EmbeddingClient(
        config=EmbeddingConfig(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="text-embedding-demo",
        ),
        client=fake_client,
    )

    assert client.embed_texts([]) == []
    assert embeddings_api.calls == []


def test_embedding_client_wraps_sdk_errors():
    class FailingEmbeddingApi:
        def create(self, model: str, input: list[str]):
            raise RuntimeError("provider down")

    fake_client = SimpleNamespace(embeddings=FailingEmbeddingApi())
    client = EmbeddingClient(
        config=EmbeddingConfig(
            api_key="test-key",
            base_url="https://example.com/v1",
            model="text-embedding-demo",
        ),
        client=fake_client,
    )

    with pytest.raises(EmbeddingError, match="embedding 调用失败"):
        client.embed_texts(["会失败的文本"])

