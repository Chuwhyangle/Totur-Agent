"""Workspace lifecycle API routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.db.models import WorkspaceRecord
from app.schemas.workspaces import (
    CreateWorkspaceRequest,
    AgentInstructionsRequest,
    AgentInstructionsResponse,
    WorkspaceItem,
    WorkspaceListResponse,
)
from app.services.workspaces.workspace_service import (
    InvalidWorkspaceError,
    WorkspaceArchivedError,
    WorkspaceNotFoundError,
    WorkspaceService,
)


router = APIRouter(tags=["workspaces"])
workspace_service = WorkspaceService()


@router.post(
    "/workspaces",
    response_model=WorkspaceItem,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(request: CreateWorkspaceRequest) -> WorkspaceItem:
    """Create an ACTIVE Workspace owned by user_id."""

    try:
        record = workspace_service.create_workspace(
            user_id=request.user_id,
            name=request.name,
            description=request.description,
        )
    except InvalidWorkspaceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "invalid_workspace", "message": str(error)},
        ) from error
    return _workspace_item_from_record(record)


@router.get("/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> WorkspaceListResponse:
    """List only the Workspaces owned by user_id."""

    records = workspace_service.list_owned_workspaces(user_id=user_id, limit=limit)
    return WorkspaceListResponse(
        user_id=user_id,
        items=[_workspace_item_from_record(record) for record in records],
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceItem)
def get_workspace(
    workspace_id: str,
    user_id: str = Query(..., min_length=1),
) -> WorkspaceItem:
    """Get an owned Workspace without exposing ownership information."""

    try:
        record = workspace_service.get_owned_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    return _workspace_item_from_record(record)


@router.post(
    "/workspaces/{workspace_id}/archive",
    response_model=WorkspaceItem,
)
def archive_workspace(
    workspace_id: str,
    user_id: str = Query(..., min_length=1),
) -> WorkspaceItem:
    """Archive an owned Workspace; repeated archive is idempotent."""

    try:
        record = workspace_service.archive_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    return _workspace_item_from_record(record)


@router.post(
    "/workspaces/{workspace_id}/restore",
    response_model=WorkspaceItem,
)
def restore_workspace(
    workspace_id: str,
    user_id: str = Query(..., min_length=1),
) -> WorkspaceItem:
    """Restore an owned Workspace; repeated restore is idempotent."""

    try:
        record = workspace_service.restore_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    return _workspace_item_from_record(record)


@router.get(
    "/workspaces/{workspace_id}/agent-instructions",
    response_model=AgentInstructionsResponse,
)
def get_agent_instructions(
    workspace_id: str,
    user_id: str = Query(..., min_length=1),
) -> AgentInstructionsResponse:
    try:
        record = workspace_service.get_agent_instructions(
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    except WorkspaceArchivedError as error:
        raise HTTPException(status_code=409, detail={"error": "workspace_archived", "workspace_id": error.workspace_id}) from error
    return AgentInstructionsResponse(
        workspace_id=record.id,
        content=record.agent_instructions,
        version=record.agent_instructions_version,
    )


@router.put(
    "/workspaces/{workspace_id}/agent-instructions",
    response_model=AgentInstructionsResponse,
)
def save_agent_instructions(
    workspace_id: str,
    request: AgentInstructionsRequest,
) -> AgentInstructionsResponse:
    try:
        record = workspace_service.save_agent_instructions(
            user_id=request.user_id,
            workspace_id=workspace_id,
            instructions=request.content,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    except WorkspaceArchivedError as error:
        raise HTTPException(status_code=409, detail={"error": "workspace_archived", "workspace_id": error.workspace_id}) from error
    except InvalidWorkspaceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "invalid_agent_instructions", "message": str(error)},
        ) from error
    return AgentInstructionsResponse(
        workspace_id=record.id,
        content=record.agent_instructions,
        version=record.agent_instructions_version,
    )


@router.delete(
    "/workspaces/{workspace_id}/agent-instructions",
    response_model=AgentInstructionsResponse,
)
def delete_agent_instructions(
    workspace_id: str,
    user_id: str = Query(..., min_length=1),
) -> AgentInstructionsResponse:
    try:
        record = workspace_service.clear_agent_instructions(
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as error:
        raise _workspace_not_found() from error
    except WorkspaceArchivedError as error:
        raise HTTPException(status_code=409, detail={"error": "workspace_archived", "workspace_id": error.workspace_id}) from error
    return AgentInstructionsResponse(
        workspace_id=record.id,
        content=record.agent_instructions,
        version=record.agent_instructions_version,
    )


def _workspace_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Workspace not found",
    )


def _workspace_item_from_record(record: WorkspaceRecord) -> WorkspaceItem:
    return WorkspaceItem(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        description=record.description,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
        agent_instructions=record.agent_instructions,
        agent_instructions_version=record.agent_instructions_version,
    )
