"""Session binding and archived Workspace chat behavior."""

import importlib
import sys

from fastapi.testclient import TestClient

from app.repositories.session_repository import create_session, get_session

def _load_enabled_app(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main").app


def test_existing_and_unbound_sessions_keep_workspace_null(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session = create_session("alice", "Legacy")

    assert session.workspace_id is None
    assert get_session(session.id).workspace_id is None


def test_create_session_binds_owned_active_workspace(monkeypatch, tmp_path):
    app = _load_enabled_app(monkeypatch)

    with TestClient(app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Project"},
        ).json()
        response = client.post(
            "/sessions",
            json={
                "user_id": "alice",
                "title": "Bound session",
                "workspace_id": workspace["id"],
            },
        )

        assert response.status_code == 201
        assert response.json()["workspace_id"] == workspace["id"]

        listed = client.get("/sessions?user_id=alice")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["workspace_id"] == workspace["id"]


def test_create_session_hides_missing_and_foreign_workspace(monkeypatch):
    app = _load_enabled_app(monkeypatch)

    with TestClient(app) as client:
        missing = client.post(
            "/sessions",
            json={
                "user_id": "alice",
                "workspace_id": "missing",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Workspace not found"

        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Private"},
        ).json()
        foreign = client.post(
            "/sessions",
            json={
                "user_id": "bob",
                "workspace_id": workspace["id"],
            },
        )
        assert foreign.status_code == 404
        assert foreign.json()["detail"] == "Workspace not found"


def test_archived_workspace_rejects_session_creation(monkeypatch):
    app = _load_enabled_app(monkeypatch)

    with TestClient(app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Archived project"},
        ).json()
        archive = client.post(
            f"/workspaces/{workspace['id']}/archive?user_id=alice"
        )
        assert archive.status_code == 200

        response = client.post(
            "/sessions",
            json={
                "user_id": "alice",
                "workspace_id": workspace["id"],
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "workspace_archived",
        "workspace_id": workspace["id"],
    }


def test_archived_workspace_rejects_chat_but_history_remains_readable(
    monkeypatch,
):
    app = _load_enabled_app(monkeypatch)

    with TestClient(app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Read-only project"},
        ).json()
        session = client.post(
            "/sessions",
            json={
                "user_id": "alice",
                "workspace_id": workspace["id"],
            },
        ).json()
        client.post(f"/workspaces/{workspace['id']}/archive?user_id=alice")

        chat = client.post(
            "/chat",
            json={
                "user_id": "alice",
                "session_id": session["id"],
                "message": "continue",
                "model_id": "ds-flash-fast",
            },
        )
        history = client.get(f"/sessions/{session['id']}/conversations")

    assert chat.status_code == 409
    assert chat.json()["detail"] == {
        "error": "workspace_archived",
        "workspace_id": workspace["id"],
    }
    assert history.status_code == 200
    assert history.json()["items"] == []
