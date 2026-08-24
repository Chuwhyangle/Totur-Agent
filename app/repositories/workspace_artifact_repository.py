"""Database operations for Workspace Artifacts and their sources."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import ARTIFACT_SOURCES_TABLE, ARTIFACTS_TABLE, ArtifactRecord, ArtifactSourceRecord


_ARTIFACT_COLUMNS = "id, workspace_id, task_id, created_by_step_id, artifact_series_id, supersedes_artifact_id, version_number, title, media_type, storage_key, size_bytes, content_hash, creation_key, status, error_code, created_at, updated_at, deleted_at"


def create_artifact(record: ArtifactRecord, *, conn: Connection | None = None) -> ArtifactRecord:
    _execute(
        f"""INSERT INTO {ARTIFACTS_TABLE} ({_ARTIFACT_COLUMNS}) VALUES
        (:id, :workspace_id, :task_id, :created_by_step_id, :artifact_series_id, :supersedes_artifact_id, :version_number, :title, :media_type, :storage_key, :size_bytes, :content_hash, :creation_key, :status, :error_code, :created_at, :updated_at, :deleted_at)""",
        {key: getattr(record, key).value if key == "status" else getattr(record, key) for key in _ARTIFACT_COLUMNS.split(", ")}, conn=conn, write=True,
    )
    return record


def get_artifact(artifact_id: str, *, conn: Connection | None = None) -> ArtifactRecord | None:
    row = _fetch_one(f"SELECT {_ARTIFACT_COLUMNS} FROM {ARTIFACTS_TABLE} WHERE id = :id", {"id": artifact_id}, conn=conn)
    return _from_row(row) if row else None


def get_by_creation_key(creation_key: str, *, conn: Connection | None = None) -> ArtifactRecord | None:
    row = _fetch_one(f"SELECT {_ARTIFACT_COLUMNS} FROM {ARTIFACTS_TABLE} WHERE creation_key = :creation_key", {"creation_key": creation_key}, conn=conn)
    return _from_row(row) if row else None


def list_workspace_artifacts(workspace_id: str, *, limit: int = 50, conn: Connection | None = None) -> list[ArtifactRecord]:
    rows = _fetch_all(f"SELECT {_ARTIFACT_COLUMNS} FROM {ARTIFACTS_TABLE} WHERE workspace_id = :workspace_id ORDER BY created_at DESC, id DESC LIMIT :limit", {"workspace_id": workspace_id, "limit": limit}, conn=conn)
    return [_from_row(row) for row in rows]


def list_task_artifacts(task_id: str, *, conn: Connection | None = None) -> list[ArtifactRecord]:
    rows = _fetch_all(f"SELECT {_ARTIFACT_COLUMNS} FROM {ARTIFACTS_TABLE} WHERE task_id = :task_id ORDER BY version_number", {"task_id": task_id}, conn=conn)
    return [_from_row(row) for row in rows]


def mark_ready(artifact_id: str, *, storage_key: str, size_bytes: int, content_hash: str, conn: Connection | None = None) -> bool:
    result = _execute(f"UPDATE {ARTIFACTS_TABLE} SET storage_key = :storage_key, size_bytes = :size_bytes, content_hash = :content_hash, status = 'READY', updated_at = :updated_at, error_code = NULL WHERE id = :id AND status = 'CREATING'", {"id": artifact_id, "storage_key": storage_key, "size_bytes": size_bytes, "content_hash": content_hash, "updated_at": _now()}, conn=conn, write=True)
    return result.rowcount == 1


def mark_failed(artifact_id: str, *, error_code: str, conn: Connection | None = None) -> bool:
    result = _execute(f"UPDATE {ARTIFACTS_TABLE} SET status = 'FAILED', error_code = :error_code, updated_at = :updated_at WHERE id = :id AND status = 'CREATING'", {"id": artifact_id, "error_code": error_code, "updated_at": _now()}, conn=conn, write=True)
    return result.rowcount == 1


def insert_source(record: ArtifactSourceRecord, *, conn: Connection | None = None) -> ArtifactSourceRecord:
    _execute(f"INSERT INTO {ARTIFACT_SOURCES_TABLE} (artifact_id, asset_id, created_at) VALUES (:artifact_id, :asset_id, :created_at)", {"artifact_id": record.artifact_id, "asset_id": record.asset_id, "created_at": record.created_at}, conn=conn, write=True)
    return record


def list_sources(artifact_id: str, *, conn: Connection | None = None) -> list[ArtifactSourceRecord]:
    rows = _fetch_all(f"SELECT artifact_id, asset_id, created_at FROM {ARTIFACT_SOURCES_TABLE} WHERE artifact_id = :artifact_id ORDER BY asset_id", {"artifact_id": artifact_id}, conn=conn)
    return [ArtifactSourceRecord(**dict(row)) for row in rows]


def _from_row(row) -> ArtifactRecord:
    return ArtifactRecord(**dict(row))


def _execute(sql: str, params: dict[str, object], *, conn: Connection | None, write: bool):
    if conn is not None:
        return conn.execute(text(sql), params)
    context = get_engine().begin() if write else get_engine().connect()
    with context as connection:
        return connection.execute(text(sql), params)


def _fetch_one(sql: str, params: dict[str, object], *, conn: Connection | None):
    return _execute(sql, params, conn=conn, write=False).mappings().fetchone()


def _fetch_all(sql: str, params: dict[str, object], *, conn: Connection | None):
    return _execute(sql, params, conn=conn, write=False).mappings().fetchall()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
