"""Database operations for Workspace assets."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import (
    WORKSPACE_ASSETS_TABLE,
    WorkspaceAssetRecord,
    WorkspaceAssetStatus,
)


_COLUMNS = """
    id, workspace_id, original_filename, media_type, size_bytes,
    storage_key, parsed_storage_key, content_hash, dedupe_key, status,
    parser_name, parser_version, error_code, error_message,
    created_at, updated_at, deleted_at
"""
_COLUMN_NAMES = (
    "id", "workspace_id", "original_filename", "media_type", "size_bytes",
    "storage_key", "parsed_storage_key", "content_hash", "dedupe_key", "status",
    "parser_name", "parser_version", "error_code", "error_message",
    "created_at", "updated_at", "deleted_at",
)
_QUALIFIED_COLUMNS = ", ".join(f"a.{name}" for name in _COLUMN_NAMES)


def insert_staging_asset(record: WorkspaceAssetRecord, *, conn: Connection | None = None) -> WorkspaceAssetRecord:
    sql = f"""
        INSERT INTO {WORKSPACE_ASSETS_TABLE} (
            id, workspace_id, original_filename, media_type, size_bytes,
            storage_key, parsed_storage_key, content_hash, dedupe_key, status,
            parser_name, parser_version, error_code, error_message,
            created_at, updated_at, deleted_at
        ) VALUES (
            :id, :workspace_id, :original_filename, :media_type, :size_bytes,
            :storage_key, :parsed_storage_key, :content_hash, :dedupe_key, :status,
            :parser_name, :parser_version, :error_code, :error_message,
            :created_at, :updated_at, :deleted_at
        )
    """
    _run(sql, _params(record), conn=conn, write=True)
    return record


def get_asset(asset_id: str, *, conn: Connection | None = None) -> WorkspaceAssetRecord | None:
    row = _fetch_one(f"SELECT {_COLUMNS} FROM {WORKSPACE_ASSETS_TABLE} WHERE id = :id", {"id": asset_id}, conn=conn)
    return _from_row(row) if row else None


def get_owned_asset(asset_id: str, user_id: str, *, conn: Connection | None = None) -> WorkspaceAssetRecord | None:
    row = _fetch_one(
        f"""SELECT {_QUALIFIED_COLUMNS}
        FROM {WORKSPACE_ASSETS_TABLE} a
        JOIN workspaces w ON w.id = a.workspace_id
        WHERE a.id = :id AND w.user_id = :user_id""",
        {"id": asset_id, "user_id": user_id},
        conn=conn,
    )
    return _from_row(row) if row else None


def list_workspace_assets(workspace_id: str, *, status: str | None = None, media_type: str | None = None, limit: int = 50, conn: Connection | None = None) -> list[WorkspaceAssetRecord]:
    clauses = ["workspace_id = :workspace_id"]
    params: dict[str, object] = {"workspace_id": workspace_id, "limit": limit}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if media_type:
        clauses.append("media_type = :media_type")
        params["media_type"] = media_type
    rows = _fetch_all(
        f"SELECT {_COLUMNS} FROM {WORKSPACE_ASSETS_TABLE} WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, id DESC LIMIT :limit",
        params,
        conn=conn,
    )
    return [_from_row(row) for row in rows]


def get_active_asset_by_hash(workspace_id: str, content_hash: str, *, conn: Connection | None = None) -> WorkspaceAssetRecord | None:
    row = _fetch_one(
        f"SELECT {_COLUMNS} FROM {WORKSPACE_ASSETS_TABLE} WHERE workspace_id = :workspace_id AND dedupe_key = :content_hash",
        {"workspace_id": workspace_id, "content_hash": content_hash}, conn=conn,
    )
    return _from_row(row) if row else None


def count_active_assets(workspace_id: str, *, conn: Connection | None = None) -> int:
    row = _fetch_one(
        f"SELECT COUNT(*) AS total FROM {WORKSPACE_ASSETS_TABLE} WHERE workspace_id = :workspace_id AND status <> :deleted",
        {"workspace_id": workspace_id, "deleted": WorkspaceAssetStatus.DELETED.value}, conn=conn,
    )
    return int(row["total"]) if row else 0


def mark_processing(asset_id: str, *, storage_key: str | None = None, expected_status: str = "STAGING", conn: Connection | None = None) -> bool:
    values = {"status": "PROCESSING", "error_code": None, "error_message": None}
    if storage_key is not None:
        values["storage_key"] = storage_key
    return _cas(asset_id, expected_status, values, conn=conn)


def mark_ready(asset_id: str, *, parsed_storage_key: str, parser_name: str, parser_version: str, conn: Connection | None = None) -> bool:
    return _cas(asset_id, "PROCESSING", {"status": "READY", "parsed_storage_key": parsed_storage_key, "parser_name": parser_name, "parser_version": parser_version, "error_code": None, "error_message": None}, conn=conn)


def mark_failed(asset_id: str, *, error_code: str, error_message: str | None = None, expected_status: str | None = None, conn: Connection | None = None) -> bool:
    values = {"status": "FAILED", "error_code": error_code, "error_message": (error_message or "")[:512]}
    if expected_status:
        return _cas(asset_id, expected_status, values, conn=conn)
    return _update(asset_id, values, conn=conn)


def claim_retry(asset_id: str, *, conn: Connection | None = None) -> bool:
    return _cas(asset_id, "FAILED", {"status": "PROCESSING", "error_code": None, "error_message": None}, conn=conn)


def claim_delete(asset_id: str, *, conn: Connection | None = None) -> bool:
    return _cas(asset_id, "READY", {"status": "DELETING"}, conn=conn) or _cas(asset_id, "FAILED", {"status": "DELETING"}, conn=conn)


def mark_deleted(asset_id: str, *, conn: Connection | None = None) -> bool:
    return _cas(asset_id, "DELETING", {"status": "DELETED", "storage_key": None, "parsed_storage_key": None, "dedupe_key": None, "deleted_at": _now()}, conn=conn)


def list_stale_assets(cutoff: str, *, limit: int = 50, conn: Connection | None = None) -> list[WorkspaceAssetRecord]:
    rows = _fetch_all(
        f"SELECT {_COLUMNS} FROM {WORKSPACE_ASSETS_TABLE} WHERE (status = :staging OR status = :processing OR status = :deleting) AND updated_at < :cutoff ORDER BY updated_at LIMIT :limit",
        {"staging": "STAGING", "processing": "PROCESSING", "deleting": "DELETING", "cutoff": cutoff, "limit": limit}, conn=conn,
    )
    return [_from_row(row) for row in rows]


def is_asset_used_by_running_task(asset_id: str, *, conn: Connection | None = None) -> bool:
    row = _fetch_one(
        """SELECT 1 AS present FROM task_asset_refs r JOIN tasks t ON t.id = r.task_id
        WHERE r.asset_id = :asset_id AND t.status = 'RUNNING' LIMIT 1""",
        {"asset_id": asset_id}, conn=conn,
    )
    return row is not None


def _cas(asset_id: str, expected_status: str, values: dict[str, object], *, conn: Connection | None) -> bool:
    values = dict(values)
    values["id"] = asset_id
    values["expected_status"] = expected_status
    values["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in values if key not in {"id", "expected_status"})
    result = _run(f"UPDATE {WORKSPACE_ASSETS_TABLE} SET {assignments} WHERE id = :id AND status = :expected_status", values, conn=conn, write=True)
    return result.rowcount == 1


def _update(asset_id: str, values: dict[str, object], *, conn: Connection | None) -> bool:
    values = dict(values)
    values["id"] = asset_id
    values["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in values if key != "id")
    result = _run(f"UPDATE {WORKSPACE_ASSETS_TABLE} SET {assignments} WHERE id = :id", values, conn=conn, write=True)
    return result.rowcount == 1


def _run(sql: str, params: dict[str, object], *, conn: Connection | None, write: bool):
    if conn is not None:
        return conn.execute(text(sql), params)
    context = get_engine().begin() if write else get_engine().connect()
    with context as connection:
        return connection.execute(text(sql), params)


def _fetch_one(sql: str, params: dict[str, object], *, conn: Connection | None):
    result = _run(sql, params, conn=conn, write=False)
    return result.mappings().fetchone()


def _fetch_all(sql: str, params: dict[str, object], *, conn: Connection | None):
    result = _run(sql, params, conn=conn, write=False)
    return result.mappings().fetchall()


def _params(record: WorkspaceAssetRecord) -> dict[str, object]:
    return {key: getattr(record, key).value if key == "status" else getattr(record, key) for key in (
        "id", "workspace_id", "original_filename", "media_type", "size_bytes", "storage_key", "parsed_storage_key", "content_hash", "dedupe_key", "status", "parser_name", "parser_version", "error_code", "error_message", "created_at", "updated_at", "deleted_at"
    )}


def _from_row(row) -> WorkspaceAssetRecord:
    return WorkspaceAssetRecord(**{key: row[key] for key in (
        "id", "workspace_id", "original_filename", "media_type", "size_bytes", "storage_key", "parsed_storage_key", "content_hash", "dedupe_key", "status", "parser_name", "parser_version", "error_code", "error_message", "created_at", "updated_at", "deleted_at"
    )})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
