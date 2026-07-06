"""Tests for v0.2 prompt persona support."""

import json

from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.db import database
from app.main import app


client = TestClient(app)


def use_temp_database(monkeypatch, tmp_path):
    """让聊天接口测试使用临时 SQLite 数据库。"""

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def final_reply() -> str:
    """返回符合 TutorReply schema 的模拟模型输出。"""

    return json.dumps(
        {
            "answer": "Persona answer",
            "next_task": "Persona task",
            "exercise": "Persona exercise",
            "checkpoints": ["Persona checkpoint"],
        },
        ensure_ascii=False,
    )


def test_get_personas_returns_builtin_prompt_profiles():
    """AC7：GET /personas 返回全部内置人设，且不暴露 system prompt。"""

    response = client.get("/personas")

    assert response.status_code == 200
    personas = response.json()
    persona_ids = [persona["persona_id"] for persona in personas]
    assert persona_ids == ["tutor", "algorithm_coach", "interviewer"]
    assert all({"persona_id", "name", "description"} == set(persona) for persona in personas)
    assert all("system_prompt" not in persona for persona in personas)


def test_chat_uses_algorithm_coach_persona_prompt(monkeypatch, tmp_path):
    """AC5：persona_id=algorithm_coach 时，模型收到算法教练 system prompt。"""

    use_temp_database(monkeypatch, tmp_path)
    captured_messages = []

    def fake_call_model(messages):
        """捕获发给模型的 messages，用于断言 system prompt。"""

        captured_messages.extend(messages)
        return final_reply()

    monkeypatch.setattr(
        chat_route.tutor_agent_service.react_orchestrator,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "persona-user",
            "message": "帮我练一道二分查找题。",
            "persona_id": "algorithm_coach",
        },
    )

    assert response.status_code == 200
    assert captured_messages[0]["role"] == "system"
    assert "算法教练" in captured_messages[0]["content"]
    assert "不要直接给出完整答案" in captured_messages[0]["content"]


def test_chat_rejects_unknown_persona_with_available_personas(monkeypatch, tmp_path):
    """AC6：无效 persona_id 返回 422，并告诉调用方可用人设。"""

    use_temp_database(monkeypatch, tmp_path)

    response = client.post(
        "/chat",
        json={
            "user_id": "persona-user",
            "message": "换一个不存在的人设。",
            "persona_id": "ghost",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "invalid_persona_id",
        "persona_id": "ghost",
        "available_personas": ["tutor", "algorithm_coach", "interviewer"],
    }
