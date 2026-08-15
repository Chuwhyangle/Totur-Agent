"""Tests for GET /models."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as config_module
import app.services.agent.model_registry as registry
from app.api.routes.models import router as models_router


def test_get_models_returns_only_public_available_metadata(monkeypatch):
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(registry, "load_dotenv", lambda: None)
    monkeypatch.setenv("ENABLED_MODELS", "ds-flash-fast,ds-pro-deep")
    monkeypatch.setenv("DEFAULT_MODEL_ID", "ds-pro-deep")
    monkeypatch.setenv("DEEPSEEK_KEY", "secret-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://secret.example.test/v1")

    test_app = FastAPI()
    test_app.include_router(models_router)
    response = TestClient(test_app).get("/models")

    assert response.status_code == 200
    assert response.json() == [
        {
            "model_id": "ds-flash-fast",
            "display_name": "DeepSeek Flash · 快速",
            "description": "不开思考，延迟最低，适合日常问答",
            "supports_thinking": False,
            "is_default": False,
        },
        {
            "model_id": "ds-pro-deep",
            "display_name": "DeepSeek Pro · 深度思考",
            "description": "最强推理，适合复杂架构与算法问题",
            "supports_thinking": True,
            "is_default": True,
        },
    ]
    assert "secret-deepseek-key" not in response.text
    assert "secret.example.test" not in response.text
    assert "deepseek-v4" not in response.text
    assert all(
        set(model)
        == {
            "model_id",
            "display_name",
            "description",
            "supports_thinking",
            "is_default",
        }
        for model in response.json()
    )


def test_main_application_registers_models_route():
    from app.main import app

    assert "/models" in app.openapi()["paths"]
