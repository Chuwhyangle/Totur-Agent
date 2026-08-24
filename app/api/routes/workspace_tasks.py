"""Read-only Workspace Task API."""

from fastapi import APIRouter, HTTPException, Query

from app.db.models import WorkspaceAssetRecord
from app.repositories import workspace_artifact_repository as artifact_repository
from app.repositories import workspace_asset_repository as asset_repository
from app.schemas.workspace_artifacts import WorkspaceArtifactItem, WorkspaceArtifactSourceItem
from app.schemas.workspace_assets import WorkspaceAssetItem
from app.schemas.workspace_tasks import WorkspaceTaskItem, WorkspaceTaskListResponse, WorkspaceTaskStepItem
from app.services.workspaces.task_service import TaskNotFoundError, TaskService
from app.services.workspaces.workspace_service import WorkspaceNotFoundError


router = APIRouter(tags=["workspace-tasks"])
task_service = TaskService()


@router.get("/workspaces/{workspace_id}/tasks", response_model=WorkspaceTaskListResponse)
def list_tasks(workspace_id: str, user_id: str = Query(..., min_length=1), limit: int = Query(default=50, ge=1, le=100)) -> WorkspaceTaskListResponse:
    try:
        records = task_service.list_tasks(user_id=user_id, workspace_id=workspace_id, limit=limit)
    except WorkspaceNotFoundError as exc:
        raise _not_found() from exc
    return WorkspaceTaskListResponse(items=[_task_item(record, include_children=True) for record in records])


@router.get("/workspaces/{workspace_id}/tasks/{task_id}", response_model=WorkspaceTaskItem)
def get_task(workspace_id: str, task_id: str, user_id: str = Query(..., min_length=1)) -> WorkspaceTaskItem:
    try:
        record = task_service.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
    except (WorkspaceNotFoundError, TaskNotFoundError) as exc:
        raise _not_found() from exc
    return _task_item(record, include_children=True)


def _task_item(record, *, include_children: bool) -> WorkspaceTaskItem:
    steps = [WorkspaceTaskStepItem(**step.__dict__) for step in task_service.list_steps(record.id)] if include_children else []
    refs = task_service.list_asset_refs(record.id) if include_children else []
    assets = []
    for ref in refs:
        asset = asset_repository.get_asset(ref.asset_id)
        if asset:
            assets.append(_asset_item(asset))
    artifacts = [_artifact_item(artifact) for artifact in artifact_repository.list_task_artifacts(record.id)] if include_children else []
    return WorkspaceTaskItem(
        id=record.id, workspace_id=record.workspace_id, session_id=record.session_id, trace_id=record.trace_id,
        goal=record.goal, status=record.status, warning_count=record.warning_count, error_code=record.error_code,
        started_at=record.started_at, finished_at=record.finished_at, created_at=record.created_at,
        updated_at=record.updated_at, steps=steps, assets=assets, artifacts=artifacts,
    )


def _asset_item(record) -> WorkspaceAssetItem:
    return WorkspaceAssetItem(
        id=record.id, workspace_id=record.workspace_id, original_filename=record.original_filename,
        media_type=record.media_type, size_bytes=record.size_bytes, content_hash=record.content_hash,
        status=record.status, parser_name=record.parser_name, parser_version=record.parser_version,
        error_code=record.error_code, error_message=record.error_message, created_at=record.created_at,
        updated_at=record.updated_at, deleted_at=record.deleted_at,
    )


def _artifact_item(record) -> WorkspaceArtifactItem:
    sources = []
    for source in artifact_repository.list_sources(record.id):
        asset = asset_repository.get_asset(source.asset_id)
        sources.append(WorkspaceArtifactSourceItem(
            asset_id=source.asset_id,
            original_filename=asset.original_filename if asset else None,
            status=asset.status if asset else None,
        ))
    return WorkspaceArtifactItem(
        id=record.id, workspace_id=record.workspace_id, task_id=record.task_id,
        created_by_step_id=record.created_by_step_id, artifact_series_id=record.artifact_series_id,
        supersedes_artifact_id=record.supersedes_artifact_id, version_number=record.version_number,
        title=record.title, media_type=record.media_type, size_bytes=record.size_bytes,
        content_hash=record.content_hash, status=record.status, error_code=record.error_code,
        created_at=record.created_at, updated_at=record.updated_at, sources=sources,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Task not found")
