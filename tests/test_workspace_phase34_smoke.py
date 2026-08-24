"""Focused smoke coverage for the Workspace phase 3/4 public contracts."""

import json
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from app.repositories import workspace_asset_repository
from app.services.workspaces.artifact_service import ArtifactValidationError, ArtifactService
from app.services.workspaces.storage import WorkspaceStorage
from app.services.workspaces.task_service import TaskService


def _load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main").app


def test_asset_upload_normalizes_mime_and_deduplicates(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        workspace = client.post(
            "/workspaces", json={"user_id": "alice", "name": "Phase 34"}
        ).json()
        url = f"/workspaces/{workspace['id']}/assets?user_id=alice"
        first = client.post(
            url,
            files={"file": ("notes.md", b"# One\n# Two\ntext", "TEXT/MARKDOWN")},
        )
        duplicate = client.post(
            url,
            files={"file": ("copy.md", b"# One\n# Two\ntext", "text/markdown")},
        )

    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert first.json()["asset"]["media_type"] == "text/markdown"
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    asset = workspace_asset_repository.get_asset(first.json()["asset"]["id"])
    payload = WorkspaceStorage().resolve(asset.parsed_storage_key).read_text(
        encoding="utf-8"
    )
    parsed = json.loads(payload)
    ids = [segment["segment_id"] for segment in parsed["segments"]]
    assert ids == [f"s{index:06d}" for index in range(1, len(ids) + 1)]
    assert len(ids) == len(set(ids))


def test_task_step_and_artifact_idempotency_and_versions(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        workspace_id = client.post(
            "/workspaces", json={"user_id": "alice", "name": "Phase 34"}
        ).json()["id"]
        session_id = client.post(
            "/sessions",
            json={"user_id": "alice", "workspace_id": workspace_id},
        ).json()["id"]
        asset_id = client.post(
            f"/workspaces/{workspace_id}/assets?user_id=alice",
            files={"file": ("source.txt", b"source", "text/plain")},
        ).json()["asset"]["id"]

    tasks = TaskService()
    task = tasks.create_task(
        user_id="alice",
        workspace_id=workspace_id,
        session_id=session_id,
        trace_id="phase34-trace",
        goal="build report",
    )
    first_step = tasks.create_step(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        tool_call_id="call-1",
        step_type="tool",
        tool_name="read_workspace_asset",
    )
    same_step = tasks.create_step(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        tool_call_id="call-1",
        step_type="tool",
        tool_name="ignored",
    )
    assert first_step.id == same_step.id

    artifacts = ArtifactService()
    first = artifacts.create_artifact(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        created_by_step_id=first_step.id,
        tool_call_id="artifact-1",
        title="Report",
        content="# v1",
        source_asset_ids=[asset_id],
    )
    same = artifacts.create_artifact(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        created_by_step_id=first_step.id,
        tool_call_id="artifact-1",
        title="Ignored",
        content="# ignored",
    )
    assert same.id == first.id

    second_step = tasks.create_step(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        tool_call_id="call-2",
        step_type="tool",
        tool_name="create_markdown_artifact",
    )
    second = artifacts.create_artifact(
        user_id="alice",
        workspace_id=workspace_id,
        task_id=task.id,
        created_by_step_id=second_step.id,
        tool_call_id="artifact-2",
        title="Report",
        content="# v2",
        supersedes_artifact_id=first.id,
    )
    assert second.version_number == 2
    assert second.artifact_series_id == first.artifact_series_id
    assert second.supersedes_artifact_id == first.id


def test_artifact_rejects_cross_workspace_source(monkeypatch, tmp_path):
    app = _load_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        first_workspace = client.post(
            "/workspaces", json={"user_id": "alice", "name": "One"}
        ).json()["id"]
        second_workspace = client.post(
            "/workspaces", json={"user_id": "alice", "name": "Two"}
        ).json()["id"]
        session_id = client.post(
            "/sessions",
            json={"user_id": "alice", "workspace_id": first_workspace},
        ).json()["id"]
        asset_id = client.post(
            f"/workspaces/{second_workspace}/assets?user_id=alice",
            files={"file": ("source.txt", b"source", "text/plain")},
        ).json()["asset"]["id"]

    tasks = TaskService()
    task = tasks.create_task(
        user_id="alice",
        workspace_id=first_workspace,
        session_id=session_id,
        trace_id="cross-workspace-trace",
        goal="reject source",
    )
    step = tasks.create_step(
        user_id="alice",
        workspace_id=first_workspace,
        task_id=task.id,
        tool_call_id="call-source",
        step_type="tool",
        tool_name="create_markdown_artifact",
    )

    with pytest.raises(ArtifactValidationError):
        ArtifactService().create_artifact(
            user_id="alice",
            workspace_id=first_workspace,
            task_id=task.id,
            created_by_step_id=step.id,
            tool_call_id="artifact-cross-workspace",
            title="Forbidden",
            content="# no",
            source_asset_ids=[asset_id],
        )
