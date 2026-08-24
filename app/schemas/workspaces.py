"""Workspace API request and response schemas."""

from pydantic import BaseModel, Field

from app.db.models import WorkspaceStatus
from app.services.workspaces.settings import (
    WORKSPACE_DESCRIPTION_MAX_LENGTH,
    WORKSPACE_NAME_MAX_LENGTH,
    WORKSPACE_USER_ID_MAX_LENGTH,
)


class CreateWorkspaceRequest(BaseModel):
    """POST /workspaces request body."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=WORKSPACE_USER_ID_MAX_LENGTH,
    )
    name: str = Field(..., min_length=1, max_length=WORKSPACE_NAME_MAX_LENGTH)
    description: str | None = Field(
        default=None,
        max_length=WORKSPACE_DESCRIPTION_MAX_LENGTH,
    )


class WorkspaceItem(BaseModel):
    """Public Workspace representation."""

    id: str
    user_id: str
    name: str
    description: str | None
    status: WorkspaceStatus
    created_at: str
    updated_at: str
    archived_at: str | None


class WorkspaceListResponse(BaseModel):
    """GET /workspaces response body."""

    user_id: str
    items: list[WorkspaceItem]
