"""Custom Persona ownership and lifecycle tests."""

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_custom_persona_can_be_created_bound_and_disabled():
    with _client() as client:
        created = client.post(
            "/personas/custom",
            json={
                "user_id": "alice",
                "name": "架构面试官",
                "description": "严格追问",
                "system_prompt": "你是一名严格的后端架构面试官。",
            },
        )
        assert created.status_code == 201
        persona_id = created.json()["persona_id"]

        listed = client.get("/personas?user_id=alice")
        assert persona_id in {item["persona_id"] for item in listed.json()}

        session = client.post(
            "/sessions",
            json={"user_id": "alice", "persona_id": persona_id},
        )
        assert session.status_code == 201

        disabled = client.delete(
            f"/personas/custom/{persona_id}?user_id=alice"
        )
        assert disabled.status_code == 204
        rejected = client.post(
            "/sessions",
            json={"user_id": "alice", "persona_id": persona_id},
        )
        assert rejected.status_code == 422


def test_custom_persona_isolation():
    with _client() as client:
        created = client.post(
            "/personas/custom",
            json={
                "user_id": "alice",
                "name": "私人导师",
                "description": "只属于 Alice",
                "system_prompt": "保持严格。",
            },
        )
        persona_id = created.json()["persona_id"]
        response = client.post(
            "/sessions",
            json={"user_id": "bob", "persona_id": persona_id},
        )
        assert response.status_code == 422
