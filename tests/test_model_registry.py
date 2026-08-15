"""Tests for the public model catalog and provider client pool."""

from concurrent.futures import ThreadPoolExecutor
import time

import pytest

import app.config as config_module
import app.services.agent.model_registry as registry
from app.clients import llm_client_pool
from app.config import ProviderConfig, load_provider_configs


@pytest.fixture(autouse=True)
def isolate_model_configuration(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(registry, "load_dotenv", lambda: None)
    llm_client_pool.close_llm_clients()
    yield
    llm_client_pool.close_llm_clients()


def test_catalog_separates_sdk_params_from_provider_extra_body():
    fast = registry.MODEL_CATALOG["ds-flash-fast"]
    deep = registry.MODEL_CATALOG["ds-pro-deep"]

    assert fast.extra_body == {"thinking": {"type": "disabled"}}
    assert fast.top_level_params == {}
    assert deep.top_level_params == {"reasoning_effort": "high"}
    assert deep.extra_body == {"thinking": {"type": "enabled"}}
    assert all(
        spec.wire_api == "chat_completions"
        for spec in registry.MODEL_CATALOG.values()
    )


def test_load_provider_configs_returns_only_complete_providers(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example.test/v1")
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")

    providers = load_provider_configs()

    assert providers == {
        "deepseek": ProviderConfig(
            api_key="deepseek-key",
            base_url="https://deepseek.example.test/v1",
        )
    }


def test_available_models_intersects_catalog_enabled_ids_and_provider(monkeypatch):
    monkeypatch.setenv(
        "ENABLED_MODELS",
        "ds-flash-fast, unknown-model, ds-pro-deep",
    )
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")

    assert list(registry.available_models()) == ["ds-flash-fast", "ds-pro-deep"]


def test_available_models_explains_missing_provider_configuration(monkeypatch):
    monkeypatch.setenv("ENABLED_MODELS", "ds-flash-fast")
    monkeypatch.delenv("DEEPSEEK_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="provider 配置不完整=.*deepseek"):
        registry.available_models()


def test_default_model_must_be_available(monkeypatch):
    monkeypatch.setenv("ENABLED_MODELS", "ds-flash-fast")
    monkeypatch.setenv("DEFAULT_MODEL_ID", "ds-pro-deep")
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")

    with pytest.raises(RuntimeError, match="DEFAULT_MODEL_ID=ds-pro-deep 不可用"):
        registry.default_model_id()


def test_resolve_model_uses_default_and_reports_invalid_ids(monkeypatch):
    monkeypatch.setenv("ENABLED_MODELS", "ds-flash-fast,ds-pro-deep")
    monkeypatch.setenv("DEFAULT_MODEL_ID", "ds-flash-fast")
    monkeypatch.setenv("DEEPSEEK_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")

    assert registry.resolve_model().model_id == "ds-flash-fast"
    assert registry.resolve_model("ds-pro-deep").model_id == "ds-pro-deep"

    with pytest.raises(registry.InvalidModelError) as exc_info:
        registry.resolve_model("missing-model")

    assert exc_info.value.model_id == "missing-model"
    assert exc_info.value.available_model_ids == ["ds-flash-fast", "ds-pro-deep"]


def test_client_pool_creates_one_client_under_concurrent_access(monkeypatch):
    created_clients = []

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url):
            time.sleep(0.01)
            self.api_key = api_key
            self.base_url = base_url
            self.closed = False
            created_clients.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(llm_client_pool, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        llm_client_pool,
        "load_provider_configs",
        lambda: {
            "deepseek": ProviderConfig(
                api_key="deepseek-key",
                base_url="https://deepseek.example.test/v1",
            )
        },
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(
            executor.map(
                lambda _: llm_client_pool.get_llm_client("deepseek"),
                range(24),
            )
        )

    assert len(created_clients) == 1
    assert all(client is clients[0] for client in clients)

    llm_client_pool.close_llm_clients()

    assert created_clients[0].closed is True
