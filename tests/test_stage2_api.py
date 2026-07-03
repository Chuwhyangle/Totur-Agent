"""API acceptance tests for the current learning stages.

These tests avoid calling the real model. The chat route is tested with a
patched model response so the API structure is stable and repeatable.
"""

from fastapi.testclient import TestClient

from app.db import database
from app.api.routes import chat as chat_route
from app.main import app
from app.repositories.conversation_repository import save_conversation


client = TestClient(app)


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def test_health_returns_service_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "tutor-agent-api",
    }


def test_chat_returns_structured_reply(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "FastAPI routes connect a URL path and HTTP method to Python code.",
      "next_task": "Create one small GET route.",
      "exercise": "Write a /hello route that returns a short JSON message.",
      "checkpoints": [
        "The response has an answer",
        "The response has a next task",
        "The checkpoints are a list"
      ]
    }
    """

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: raw_model_reply,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "What is a FastAPI route?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    reply = body["reply"]

    assert body["user_id"] == "default"
    assert body["message"] == "What is a FastAPI route?"
    assert isinstance(reply["answer"], str)
    assert isinstance(reply["next_task"], str)
    assert isinstance(reply["exercise"], str)
    assert isinstance(reply["checkpoints"], list)
    assert len(reply["checkpoints"]) == 3


def test_chat_rejects_empty_message():
    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "",
        },
    )

    assert response.status_code == 422


def test_chat_rejects_empty_user_id():
    response = client.post(
        "/chat",
        json={
            "user_id": "",
            "message": "What is FastAPI?",
        },
    )

    assert response.status_code == 422


def test_chat_falls_back_when_model_reply_is_not_json(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: "This is not JSON, but the API should still respond.",
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Explain JSON parsing.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    reply = body["reply"]

    assert reply["answer"] == "This is not JSON, but the API should still respond."
    assert isinstance(reply["next_task"], str)
    assert isinstance(reply["exercise"], str)
    assert isinstance(reply["checkpoints"], list)
    assert len(reply["checkpoints"]) == 3


def test_get_conversations_returns_recent_history_for_user(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    first_reply = """
    {
      "answer": "First answer",
      "next_task": "First task",
      "exercise": "First exercise",
      "checkpoints": ["First checkpoint"]
    }
    """
    second_reply = """
    {
      "answer": "Second answer",
      "next_task": "Second task",
      "exercise": "Second exercise",
      "checkpoints": ["Second checkpoint"]
    }
    """
    bob_reply = """
    {
      "answer": "Bob answer",
      "next_task": "Bob task",
      "exercise": "Bob exercise",
      "checkpoints": ["Bob checkpoint"]
    }
    """

    save_conversation("alice", "first question", first_reply)
    second_id = save_conversation("alice", "second question", second_reply)
    save_conversation("bob", "bob question", bob_reply)

    response = client.get("/conversations/alice")

    assert response.status_code == 200
    body = response.json()

    assert body["user_id"] == "alice"
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == second_id
    assert body["items"][0]["message"] == "second question"
    assert body["items"][0]["reply"]["answer"] == "Second answer"
    assert body["items"][1]["message"] == "first question"
    assert all(item["message"] != "bob question" for item in body["items"])


def test_get_conversations_respects_custom_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """

    save_conversation("alice", "first question", reply_json)
    save_conversation("alice", "second question", reply_json)
    third_id = save_conversation("alice", "third question", reply_json)

    response = client.get("/conversations/alice?limit=2")

    assert response.status_code == 200
    body = response.json()

    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == third_id
    assert body["items"][0]["message"] == "third question"
    assert body["items"][1]["message"] == "second question"


def test_get_conversations_rejects_invalid_limit():
    response = client.get("/conversations/alice?limit=0")

    assert response.status_code == 422
