"""Workspace domain use cases."""

from datetime import datetime, timezone
import re
from uuid import uuid4

from sqlalchemy import Connection

from app.db.models import WorkspaceRecord, WorkspaceStatus
from app.repositories import workspace_repository
from app.services.workspaces.settings import (
    WORKSPACE_DESCRIPTION_MAX_LENGTH,
    WORKSPACE_NAME_MAX_LENGTH,
    WORKSPACE_USER_ID_MAX_LENGTH,
)


class WorkspaceDomainError(ValueError):
    """Base exception for Workspace domain rule violations."""


class WorkspaceNotFoundError(WorkspaceDomainError):
    """The Workspace does not exist or is not owned by the requesting user."""


class WorkspaceArchivedError(WorkspaceDomainError):
    """A Workspace operation requires an ACTIVE Workspace."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"workspace {workspace_id} is archived")


class InvalidWorkspaceError(WorkspaceDomainError):
    """Workspace fields do not satisfy domain constraints."""


class WorkspaceService:
    """Application service for the first Workspace lifecycle operations."""

    def create_workspace(
        self,
        *,
        user_id: str,
        name: str,
        description: str | None = None,
        conn: Connection | None = None,
    ) -> WorkspaceRecord:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise InvalidWorkspaceError("user_id must not be blank")
        if len(normalized_user_id) > WORKSPACE_USER_ID_MAX_LENGTH:
            raise InvalidWorkspaceError(
                f"user_id must be at most {WORKSPACE_USER_ID_MAX_LENGTH} characters"
            )

        normalized_name = _normalize_whitespace(name)
        if not normalized_name:
            raise InvalidWorkspaceError("name must not be blank")
        if len(normalized_name) > WORKSPACE_NAME_MAX_LENGTH:
            raise InvalidWorkspaceError(
                f"name must be at most {WORKSPACE_NAME_MAX_LENGTH} characters"
            )

        normalized_description = _normalize_description(description)
        now = datetime.now(timezone.utc).isoformat()
        record = WorkspaceRecord(
            id=str(uuid4()),
            user_id=normalized_user_id,
            name=normalized_name,
            description=normalized_description,
            status=WorkspaceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            archived_at=None,
        )
        return workspace_repository.insert_workspace(record, conn=conn)

    def get_owned_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conn: Connection | None = None,
    ) -> WorkspaceRecord:
        record = workspace_repository.get_workspace(workspace_id, conn=conn)
        if record is None or record.user_id != user_id.strip():
            raise WorkspaceNotFoundError
        return record

    def list_owned_workspaces(
        self,
        *,
        user_id: str,
        limit: int = 50,
        conn: Connection | None = None,
    ) -> list[WorkspaceRecord]:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            return []
        return workspace_repository.list_workspaces(
            normalized_user_id,
            limit=limit,
            conn=conn,
        )

    def archive_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conn: Connection | None = None,
    ) -> WorkspaceRecord:
        record = self.get_owned_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            conn=conn,
        )
        if record.status is WorkspaceStatus.ARCHIVED:
            return record
        record.status = WorkspaceStatus.ARCHIVED
        record.archived_at = datetime.now(timezone.utc).isoformat()
        return workspace_repository.update_workspace(record, conn=conn)

    def restore_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conn: Connection | None = None,
    ) -> WorkspaceRecord:
        record = self.get_owned_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            conn=conn,
        )
        if record.status is WorkspaceStatus.ACTIVE:
            return record
        record.status = WorkspaceStatus.ACTIVE
        record.archived_at = None
        return workspace_repository.update_workspace(record, conn=conn)

    def require_active_owned_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conn: Connection | None = None,
    ) -> WorkspaceRecord:
        record = self.get_owned_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            conn=conn,
        )
        if record.status is WorkspaceStatus.ARCHIVED:
            raise WorkspaceArchivedError(workspace_id)
        return record

    def ensure_active_workspace(
        self,
        workspace_id: str,
        *,
        conn: Connection | None = None,
    ) -> None:
        record = workspace_repository.get_workspace(workspace_id, conn=conn)
        if record is not None and record.status is WorkspaceStatus.ARCHIVED:
            raise WorkspaceArchivedError(workspace_id)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_whitespace(value)
    if not normalized:
        return None
    if len(normalized) > WORKSPACE_DESCRIPTION_MAX_LENGTH:
        raise InvalidWorkspaceError(
            f"description must be at most {WORKSPACE_DESCRIPTION_MAX_LENGTH} characters"
        )
    return normalized
