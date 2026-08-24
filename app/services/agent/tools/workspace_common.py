"""Shared security and parsed-file helpers for Workspace Agent tools."""

from __future__ import annotations

import json
from typing import Any

from app.db.models import WorkspaceAssetRecord, WorkspaceAssetStatus
from app.repositories import workspace_asset_repository
from app.services.agent.workspace.context import AgentExecutionContext
from app.services.workspaces.settings import is_workspaces_enabled
from app.services.workspaces.storage import WorkspaceStorage
from app.services.workspaces.workspace_service import WorkspaceArchivedError, WorkspaceNotFoundError, WorkspaceService


class WorkspaceToolError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        super().__init__(message)


def require_workspace_context(execution_context: AgentExecutionContext | None) -> AgentExecutionContext:
    if execution_context is None or execution_context.workspace_id is None:
        raise WorkspaceToolError("workspace_context_required", "Workspace execution context is required")
    if not is_workspaces_enabled():
        raise WorkspaceToolError("workspace_disabled", "Workspace functionality is disabled")
    try:
        WorkspaceService().require_active_owned_workspace(
            user_id=execution_context.user_id,
            workspace_id=execution_context.workspace_id,
        )
    except WorkspaceArchivedError as exc:
        raise WorkspaceToolError("workspace_archived", str(exc)) from exc
    except WorkspaceNotFoundError as exc:
        raise WorkspaceToolError("workspace_context_required", "Workspace context is not owned by the user") from exc
    return execution_context


def get_ready_asset(execution_context: AgentExecutionContext, asset_id: str) -> WorkspaceAssetRecord:
    context = require_workspace_context(execution_context)
    asset = workspace_asset_repository.get_asset(asset_id)
    if asset is None or asset.workspace_id != context.workspace_id:
        raise WorkspaceToolError("asset_not_found", "Workspace Asset not found")
    if asset.status is not WorkspaceAssetStatus.READY or not asset.parsed_storage_key:
        raise WorkspaceToolError("asset_not_ready", "Workspace Asset is not ready")
    return asset


def read_parsed_asset(asset: WorkspaceAssetRecord) -> dict[str, Any]:
    try:
        path = WorkspaceStorage().path_for_download(asset.parsed_storage_key or "")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise WorkspaceToolError("asset_parse_unavailable", "Parsed Workspace Asset is unavailable") from exc
    if not isinstance(payload, dict) or payload.get("asset_id") != asset.id:
        raise WorkspaceToolError("asset_parse_unavailable", "Parsed Workspace Asset is invalid")
    return payload


def public_asset(asset: WorkspaceAssetRecord) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "filename": asset.original_filename,
        "media_type": asset.media_type,
        "size_bytes": asset.size_bytes,
        "status": asset.status.value,
        "created_at": asset.created_at,
    }
