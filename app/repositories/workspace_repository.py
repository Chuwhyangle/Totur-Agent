"""Database operations for Workspace records."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import WORKSPACES_TABLE, WorkspaceRecord


def insert_workspace(
    record: WorkspaceRecord,
    *,
    conn: Connection | None = None,
) -> WorkspaceRecord:
    """Insert a Workspace record, reusing the caller's transaction when given."""

    sql = f"""
    INSERT INTO {WORKSPACES_TABLE}
        (id, user_id, name, description, status, created_at, updated_at, archived_at)
    VALUES
        (:id, :user_id, :name, :description, :status, :created_at, :updated_at, :archived_at)
    """
    params = _workspace_params(record)

    def _execute(connection: Connection) -> None:
        connection.execute(text(sql), params)

    if conn is not None:
        _execute(conn)
    else:
        with get_engine().begin() as connection:
            _execute(connection)
    return record


def get_workspace(
    workspace_id: str,
    *,
    conn: Connection | None = None,
) -> WorkspaceRecord | None:
    """Fetch one Workspace by id."""

    sql = f"""
    SELECT id, user_id, name, description, status,
           created_at, updated_at, archived_at
    FROM {WORKSPACES_TABLE}
    WHERE id = :id
    """

    def _execute(connection: Connection):
        return connection.execute(text(sql), {"id": workspace_id}).mappings().fetchone()

    if conn is not None:
        row = _execute(conn)
    else:
        with get_engine().connect() as connection:
            row = _execute(connection)
    return _workspace_from_row(row) if row is not None else None


def list_workspaces(
    user_id: str,
    *,
    limit: int = 50,
    conn: Connection | None = None,
) -> list[WorkspaceRecord]:
    """Fetch a user's Workspaces, newest updates first."""

    sql = f"""
    SELECT id, user_id, name, description, status,
           created_at, updated_at, archived_at
    FROM {WORKSPACES_TABLE}
    WHERE user_id = :user_id
    ORDER BY updated_at DESC, id DESC
    LIMIT :limit
    """

    def _execute(connection: Connection):
        return connection.execute(
            text(sql),
            {"user_id": user_id, "limit": limit},
        ).mappings().fetchall()

    if conn is not None:
        rows = _execute(conn)
    else:
        with get_engine().connect() as connection:
            rows = _execute(connection)
    return [_workspace_from_row(row) for row in rows]


def update_workspace(
    record: WorkspaceRecord,
    *,
    conn: Connection | None = None,
) -> WorkspaceRecord:
    """Persist the mutable Workspace fields."""

    now = datetime.now(timezone.utc).isoformat()
    record.updated_at = now
    sql = f"""
    UPDATE {WORKSPACES_TABLE}
    SET name = :name,
        description = :description,
        status = :status,
        updated_at = :updated_at,
        archived_at = :archived_at
    WHERE id = :id
    """
    params = {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "status": record.status.value,
        "updated_at": record.updated_at,
        "archived_at": record.archived_at,
    }

    def _execute(connection: Connection) -> None:
        connection.execute(text(sql), params)

    if conn is not None:
        _execute(conn)
    else:
        with get_engine().begin() as connection:
            _execute(connection)
    return record


def _workspace_params(record: WorkspaceRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "name": record.name,
        "description": record.description,
        "status": record.status.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "archived_at": record.archived_at,
    }


def _workspace_from_row(row) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived_at=row["archived_at"],
    )
