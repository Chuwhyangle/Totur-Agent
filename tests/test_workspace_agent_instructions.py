"""Workspace AGENT.md persistence and ownership tests."""

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    import importlib
    import sys
    sys.modules.pop("app.main", None)
    return TestClient(importlib.import_module("app.main").app)


def test_workspace_agent_instructions_save_clear_and_version(monkeypatch):
    with _client(monkeypatch) as client:
        workspace = client.post(
            "/workspaces", json={"user_id": "alice", "name": "Interview"}
        ).json()
        workspace_id = workspace["id"]
        saved = client.put(
            f"/workspaces/{workspace_id}/agent-instructions",
            json={"user_id": "alice", "content": "先骨架后追问"},
        )
        assert saved.status_code == 200
        assert saved.json()["version"] == 1
        cleared = client.delete(
            f"/workspaces/{workspace_id}/agent-instructions?user_id=alice"
        )
        assert cleared.status_code == 200
        assert cleared.json()["content"] is None
        assert cleared.json()["version"] == 2


def test_workspace_agent_instructions_are_owner_and_active_only(monkeypatch):
    with _client(monkeypatch) as client:
        workspace = client.post(
            "/workspaces", json={"user_id": "alice", "name": "Private"}
        ).json()
        workspace_id = workspace["id"]
        assert client.get(
            f"/workspaces/{workspace_id}/agent-instructions?user_id=bob"
        ).status_code == 404
        client.post(f"/workspaces/{workspace_id}/archive?user_id=alice")
        assert client.put(
            f"/workspaces/{workspace_id}/agent-instructions",
            json={"user_id": "alice", "content": "规则"},
        ).status_code == 409
