"""Read-only Workspace Artifact API."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from app.db.models import WorkspaceAssetStatus
from app.schemas.workspace_artifacts import WorkspaceArtifactItem, WorkspaceArtifactListResponse, WorkspaceArtifactSourceItem
from app.services.workspaces.artifact_service import ArtifactNotFoundError, ArtifactService
from app.services.workspaces.workspace_service import WorkspaceNotFoundError


router = APIRouter(tags=["workspace-artifacts"])
artifact_service = ArtifactService()


@router.get("/workspaces/{workspace_id}/artifacts", response_model=WorkspaceArtifactListResponse)
def list_artifacts(workspace_id: str, user_id: str = Query(..., min_length=1), include_versions: bool = False, limit: int = Query(default=50, ge=1, le=100)) -> WorkspaceArtifactListResponse:
    try:
        records = artifact_service.list_artifacts(user_id=user_id, workspace_id=workspace_id, limit=limit, include_versions=include_versions)
    except WorkspaceNotFoundError as exc:
        raise _not_found() from exc
    return WorkspaceArtifactListResponse(items=[_item(record) for record in records])


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/content")
def read_artifact_content(workspace_id: str, artifact_id: str, user_id: str = Query(..., min_length=1)):
    try:
        _, content = artifact_service.read_content(user_id=user_id, workspace_id=workspace_id, artifact_id=artifact_id)
    except (WorkspaceNotFoundError, ArtifactNotFoundError) as exc:
        raise _not_found() from exc
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/download")
def download_artifact(workspace_id: str, artifact_id: str, user_id: str = Query(..., min_length=1)):
    try:
        record = artifact_service.get_artifact(user_id=user_id, workspace_id=workspace_id, artifact_id=artifact_id)
        if not record.storage_key or record.status.value != "READY":
            raise ArtifactNotFoundError("Artifact content is not ready")
        path = artifact_service.storage.path_for_download(record.storage_key)
    except (WorkspaceNotFoundError, ArtifactNotFoundError) as exc:
        raise _not_found() from exc
    return FileResponse(path, media_type=record.media_type, filename="report.md")


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}", response_model=WorkspaceArtifactItem)
def get_artifact(workspace_id: str, artifact_id: str, user_id: str = Query(..., min_length=1)) -> WorkspaceArtifactItem:
    try:
        return _item(artifact_service.get_artifact(user_id=user_id, workspace_id=workspace_id, artifact_id=artifact_id))
    except (WorkspaceNotFoundError, ArtifactNotFoundError) as exc:
        raise _not_found() from exc


def _item(record) -> WorkspaceArtifactItem:
    sources = []
    for source in artifact_service.list_sources(record.id):
        asset = _asset_by_id(source.asset_id)
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


def _asset_by_id(asset_id: str):
    from app.repositories.workspace_asset_repository import get_asset

    return get_asset(asset_id)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Artifact not found")
