"""Boundary contracts for Workspace kill switch, default sessions, and SSE errors."""

import importlib
import json
import sys

from fastapi.testclient import TestClient

from app.db.models import DEFAULT_SESSION_TITLE
from app.repositories.session_repository import (
    create_session,
    get_or_create_default_session,
)
from app.services.workspaces.workspace_service import WorkspaceService


def _load_main_app(monkeypatch, enabled: bool):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true" if enabled else "false")
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main").app


def test_default_session_does_not_reuse_workspace_bound_default_session(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    workspace = WorkspaceService().create_workspace(user_id="alice", name="Project")
    bound = create_session(
        user_id="alice",
        title=DEFAULT_SESSION_TITLE,
        workspace_id=workspace.id,
    )

    default_session = get_or_create_default_session("alice")

    assert default_session.id != bound.id
    assert default_session.workspace_id is None
    assert default_session.title == DEFAULT_SESSION_TITLE


def test_disabled_workspace_kill_switch_rejects_session_binding(
    monkeypatch,
):
    enabled_app = _load_main_app(monkeypatch, enabled=True)
    with TestClient(enabled_app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Project"},
        ).json()

    disabled_app = _load_main_app(monkeypatch, enabled=False)
    with TestClient(disabled_app) as client:
        response = client.post(
            "/sessions",
            json={"user_id": "alice", "workspace_id": workspace["id"]},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "workspace_disabled",
        "workspace_id": workspace["id"],
    }


def test_disabled_workspace_kill_switch_rejects_bound_chat(
    monkeypatch,
):
    enabled_app = _load_main_app(monkeypatch, enabled=True)
    with TestClient(enabled_app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Project"},
        ).json()
        session = client.post(
            "/sessions",
            json={"user_id": "alice", "workspace_id": workspace["id"]},
        ).json()

    disabled_app = _load_main_app(monkeypatch, enabled=False)
    with TestClient(disabled_app) as client:
        response = client.post(
            "/chat",
            json={
                "user_id": "alice",
                "session_id": session["id"],
                "message": "hello",
                "model_id": "ds-flash-fast",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "workspace_disabled",
        "workspace_id": workspace["id"],
    }


def test_stream_preflight_returns_http_409_for_archived_workspace(
    monkeypatch,
):
    app = _load_main_app(monkeypatch, enabled=True)
    with TestClient(app) as client:
        workspace = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "Project"},
        ).json()
        session = client.post(
            "/sessions",
            json={"user_id": "alice", "workspace_id": workspace["id"]},
        ).json()
        client.post(f"/workspaces/{workspace['id']}/archive?user_id=alice")

        response = client.post(
            "/chat/stream",
            json={
                "user_id": "alice",
                "session_id": session["id"],
                "message": "hello",
                "model_id": "ds-flash-fast",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "error": "workspace_archived",
        "workspace_id": workspace["id"],
    }


def test_stream_started_error_uses_stable_workspace_event(monkeypatch):
    from app.api.routes import chat as chat_route
    from app.services.workspaces.workspace_service import WorkspaceArchivedError
    from app.main import app

    def fake_stream(_request):
        yield {"event": "token", "data": {"text": "partial"}}
        raise WorkspaceArchivedError("workspace-id")

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", fake_stream)

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={
                "user_id": "alice",
                "message": "hello",
                "model_id": "ds-flash-fast",
            },
        )

    blocks = response.text.strip().split("\n\n")
    error_data = json.loads(next(line[6:] for line in blocks[-1].splitlines() if line.startswith("data: ")))
    assert response.status_code == 200
    assert error_data == {
        "error": "workspace_archived",
        "message": "该 Workspace 已归档。",
        "retryable": False,
        "workspace_id": "workspace-id",
    }
