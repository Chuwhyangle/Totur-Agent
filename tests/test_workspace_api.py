"""Workspace API and feature-flag mounting tests."""

import importlib
import sys

from fastapi.testclient import TestClient


def _load_main_app(monkeypatch, enabled: bool):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true" if enabled else "false")
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main").app


def test_workspace_routes_are_not_mounted_when_disabled(monkeypatch):
    app = _load_main_app(monkeypatch, enabled=False)

    with TestClient(app) as client:
        response = client.get("/workspaces?user_id=alice")

    assert response.status_code == 404


def test_workspace_api_supports_lifecycle_and_ownership(monkeypatch):
    app = _load_main_app(monkeypatch, enabled=True)

    with TestClient(app) as client:
        created = client.post(
            "/workspaces",
            json={
                "user_id": "alice",
                "name": "  My   Project ",
                "description": "  project   notes ",
            },
        )
        assert created.status_code == 201
        body = created.json()
        workspace_id = body["id"]
        assert body["name"] == "My Project"
        assert body["description"] == "project notes"
        assert body["status"] == "ACTIVE"

        listed = client.get("/workspaces?user_id=alice")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [workspace_id]

        hidden = client.get(f"/workspaces/{workspace_id}?user_id=bob")
        assert hidden.status_code == 404
        assert hidden.json()["detail"] == "Workspace not found"

        archived = client.post(
            f"/workspaces/{workspace_id}/archive?user_id=alice"
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"
        assert archived.json()["archived_at"] is not None

        archived_again = client.post(
            f"/workspaces/{workspace_id}/archive?user_id=alice"
        )
        assert archived_again.status_code == 200
        assert archived_again.json()["status"] == "ARCHIVED"

        restored = client.post(
            f"/workspaces/{workspace_id}/restore?user_id=alice"
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "ACTIVE"
        assert restored.json()["archived_at"] is None


def test_workspace_api_requires_valid_name(monkeypatch):
    app = _load_main_app(monkeypatch, enabled=True)

    with TestClient(app) as client:
        response = client.post(
            "/workspaces",
            json={"user_id": "alice", "name": "   "},
        )

    assert response.status_code == 422
