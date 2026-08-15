"""Regression tests for per-message chat model selection."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.db import database
from app.main import app
from app.services import timings
from app.services.agent import react_orchestrator as react_module
from app.services.agent.model_registry import ModelSpec
from app.services.agent.react_orchestrator import ReactOrchestrator
from app.services import summary_service as summary_module
from app.services.summary_service import SummaryService


client = TestClient(app)


FINAL_REPLY = """
{
  "answer": "Model selection works.",
  "next_task": "Continue learning.",
  "exercise": "Try another model.",
  "checkpoints": ["Model id is returned."]
}
"""


class EmptyToolRegistry:
    """Keep model-selection tests independent from production tools."""

    def get_tools_schema(self):
        return []


class CapturingCompletions:
    """Record OpenAI-compatible request kwargs and return a fixed message."""

    def __init__(self, content: str = FINAL_REPLY) -> None:
        self.calls: list[dict] = []
        self.content = content

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content, tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )


def _fake_client(content: str = FINAL_REPLY):
    completions = CapturingCompletions(content)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        completions=completions,
    )


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_chat_rejects_unavailable_model_id(path):
    response = client.post(
        path,
        json={
            "user_id": "model-user",
            "message": "hello",
            "model_id": "missing-model",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "invalid_model_id",
        "model_id": "missing-model",
        "available_models": [
            "ds-flash-fast",
            "ds-flash-think",
            "ds-pro-deep",
        ],
    }


def test_same_session_can_switch_models_without_losing_history(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "model-selection.db")
    monkeypatch.setattr(chat_route.tutor_agent_service, "seed_context_enabled", False)

    selected_models: list[str] = []
    messages_by_call: list[list[dict]] = []

    def fake_call_model_with_tools(messages):
        spec = chat_route.tutor_agent_service.react_orchestrator._model_spec_var.get()
        selected_models.append(spec.model_id)
        messages_by_call.append(messages)
        return {"content": FINAL_REPLY, "tool_calls": []}

    monkeypatch.setattr(
        chat_route.tutor_agent_service.react_orchestrator,
        "_call_model_with_tools",
        fake_call_model_with_tools,
    )

    first = client.post(
        "/chat",
        json={
            "user_id": "model-switch-user",
            "message": "Explain dependency injection.",
            "model_id": "ds-flash-fast",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/chat",
        json={
            "user_id": "model-switch-user",
            "session_id": first.json()["session_id"],
            "message": "Continue with an example.",
            "model_id": "ds-pro-deep",
        },
    )

    assert second.status_code == 200
    assert first.json()["model_id"] == "ds-flash-fast"
    assert second.json()["model_id"] == "ds-pro-deep"
    assert selected_models == ["ds-flash-fast", "ds-pro-deep"]
    assert "Explain dependency injection." in str(messages_by_call[1])
    assert "Continue with an example." in str(messages_by_call[1])


def test_react_uses_api_model_and_separates_request_params(monkeypatch):
    fake_client = _fake_client()
    monkeypatch.setattr(react_module, "get_llm_client", lambda provider: fake_client)
    spec = ModelSpec(
        model_id="public-model",
        display_name="Public Model",
        description="test",
        provider="deepseek",
        api_model="provider-model-name",
        supports_tools=True,
        supports_thinking=True,
        top_level_params={"reasoning_effort": "high"},
        extra_body={"thinking": {"type": "enabled"}},
    )
    orchestrator = ReactOrchestrator(tool_registry=EmptyToolRegistry())
    timings.start_request()

    raw_reply, _ = orchestrator.run(
        [{"role": "user", "content": "hello"}],
        model_spec=spec,
    )

    request = fake_client.completions.calls[0]
    assert raw_reply == FINAL_REPLY
    assert request["model"] == "provider-model-name"
    assert request["reasoning_effort"] == "high"
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert timings.get_meta("model") == "public-model"


def test_summary_service_uses_default_model_runtime(monkeypatch):
    fake_client = _fake_client("summary text")
    spec = ModelSpec(
        model_id="default-public-model",
        display_name="Default",
        description="test",
        provider="deepseek",
        api_model="default-provider-model",
        supports_tools=True,
        supports_thinking=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
    monkeypatch.setattr(summary_module, "resolve_model", lambda: spec)
    monkeypatch.setattr(summary_module, "get_llm_client", lambda provider: fake_client)

    result = SummaryService()._call_model([{"role": "user", "content": "history"}])

    request = fake_client.completions.calls[0]
    assert result == "summary text"
    assert request["model"] == "default-provider-model"
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
