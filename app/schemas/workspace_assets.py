"""Workspace Asset API schemas."""

from pydantic import BaseModel

from app.db.models import WorkspaceAssetStatus


class WorkspaceAssetItem(BaseModel):
    id: str
    workspace_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    content_hash: str
    status: WorkspaceAssetStatus
    parser_name: str | None
    parser_version: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None


class WorkspaceAssetListResponse(BaseModel):
    items: list[WorkspaceAssetItem]


class WorkspaceAssetUploadResponse(BaseModel):
    asset: WorkspaceAssetItem
    duplicate: bool
