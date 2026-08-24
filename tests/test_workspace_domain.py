"""Workspace repository and service tests."""

import pytest

from app.db.models import WorkspaceStatus
from app.services.workspaces.workspace_service import (
    InvalidWorkspaceError,
    WorkspaceArchivedError,
    WorkspaceNotFoundError,
    WorkspaceService,
)


@pytest.fixture
def workspace_service():
    return WorkspaceService()


def test_workspace_lifecycle_normalizes_fields_and_is_idempotent(
    workspace_service,
):
    record = workspace_service.create_workspace(
        user_id=" alice ",
        name="  My   Workspace\n",
        description="  A   useful\nproject. ",
    )

    assert record.id
    assert record.user_id == "alice"
    assert record.name == "My Workspace"
    assert record.description == "A useful project."
    assert record.status is WorkspaceStatus.ACTIVE
    assert record.archived_at is None

    archived = workspace_service.archive_workspace(
        user_id="alice",
        workspace_id=record.id,
    )
    assert archived.status is WorkspaceStatus.ARCHIVED
    assert archived.archived_at is not None

    archived_again = workspace_service.archive_workspace(
        user_id="alice",
        workspace_id=record.id,
    )
    assert archived_again.status is WorkspaceStatus.ARCHIVED
    assert archived_again.archived_at == archived.archived_at

    restored = workspace_service.restore_workspace(
        user_id="alice",
        workspace_id=record.id,
    )
    assert restored.status is WorkspaceStatus.ACTIVE
    assert restored.archived_at is None

    restored_again = workspace_service.restore_workspace(
        user_id="alice",
        workspace_id=record.id,
    )
    assert restored_again.status is WorkspaceStatus.ACTIVE
    assert restored_again.archived_at is None


def test_workspace_ownership_is_not_enumerable(workspace_service):
    record = workspace_service.create_workspace(user_id="alice", name="Private")

    with pytest.raises(WorkspaceNotFoundError):
        workspace_service.get_owned_workspace(
            user_id="bob",
            workspace_id=record.id,
        )
    with pytest.raises(WorkspaceNotFoundError):
        workspace_service.archive_workspace(
            user_id="bob",
            workspace_id=record.id,
        )
    with pytest.raises(WorkspaceNotFoundError):
        workspace_service.get_owned_workspace(
            user_id="alice",
            workspace_id="missing",
        )


def test_archived_workspace_cannot_be_required_active(workspace_service):
    record = workspace_service.create_workspace(user_id="alice", name="Project")
    workspace_service.archive_workspace(user_id="alice", workspace_id=record.id)

    with pytest.raises(WorkspaceArchivedError):
        workspace_service.require_active_owned_workspace(
            user_id="alice",
            workspace_id=record.id,
        )


def test_workspace_field_limits_are_enforced(workspace_service):
    with pytest.raises(InvalidWorkspaceError):
        workspace_service.create_workspace(user_id="alice", name="  ")
    with pytest.raises(InvalidWorkspaceError):
        workspace_service.create_workspace(user_id="u" * 65, name="valid")
    with pytest.raises(InvalidWorkspaceError):
        workspace_service.create_workspace(user_id="alice", name="x" * 121)
    with pytest.raises(InvalidWorkspaceError):
        workspace_service.create_workspace(
            user_id="alice",
            name="valid",
            description="x" * 4001,
        )


def test_list_owned_workspaces_is_isolated(workspace_service):
    workspace_service.create_workspace(user_id="alice", name="A")
    workspace_service.create_workspace(user_id="bob", name="B")

    records = workspace_service.list_owned_workspaces(user_id="alice")

    assert [record.user_id for record in records] == ["alice"]
    assert [record.name for record in records] == ["A"]
