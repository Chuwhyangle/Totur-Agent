"""Workspace Artifact API schemas."""

from pydantic import BaseModel

from app.db.models import ArtifactStatus, WorkspaceAssetStatus


class WorkspaceArtifactSourceItem(BaseModel):
    asset_id: str
    original_filename: str | None
    status: WorkspaceAssetStatus | None


class WorkspaceArtifactItem(BaseModel):
    id: str
    workspace_id: str
    task_id: str
    created_by_step_id: int
    artifact_series_id: str
    supersedes_artifact_id: str | None
    version_number: int
    title: str
    media_type: str
    size_bytes: int | None
    content_hash: str | None
    status: ArtifactStatus
    error_code: str | None
    created_at: str
    updated_at: str
    sources: list[WorkspaceArtifactSourceItem] = []


class WorkspaceArtifactListResponse(BaseModel):
    items: list[WorkspaceArtifactItem]
