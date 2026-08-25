"""Persistence operations for user-uploaded knowledge documents."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import (
    KNOWLEDGE_DOCUMENTS_TABLE,
    NON_TERMINAL_STATUSES,
    KnowledgeDocumentRecord,
    KnowledgeDocumentStatus,
)


_COLUMN_NAMES = (
    "id", "user_id", "original_filename", "media_type", "size_bytes",
    "storage_key", "file_sha256", "text_sha256", "dedupe_key", "version_no",
    "status", "page_count", "chunk_count", "parser_name", "parser_version",
    "error_code", "error_message", "created_at", "updated_at", "deleted_at",
)
_COLUMNS = ", ".join(_COLUMN_NAMES)


def insert_uploaded(
    record: KnowledgeDocumentRecord,
    *,
    conn: Connection | None = None,
) -> None:
    _execute(
        f"""
        INSERT INTO {KNOWLEDGE_DOCUMENTS_TABLE} ({_COLUMNS})
        VALUES ({', '.join(f':{column}' for column in _COLUMN_NAMES)})
        """,
        _params(record),
        conn=conn,
        write=True,
    )


def get_document(
    document_id: str,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    row = _fetch_one(
        f"SELECT {_COLUMNS} FROM {KNOWLEDGE_DOCUMENTS_TABLE} WHERE id = :id",
        {"id": document_id},
        conn=conn,
    )
    return _from_row(row) if row else None


def get_active_by_file_hash(
    user_id: str,
    file_sha256: str,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    return _get_active_hash("file_sha256", user_id, file_sha256, conn=conn)


def get_active_by_text_hash(
    user_id: str,
    text_sha256: str,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    return _get_active_hash("text_sha256", user_id, text_sha256, conn=conn)


def get_latest_by_filename(
    user_id: str,
    original_filename: str,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    row = _fetch_one(
        f"""
        SELECT {_COLUMNS} FROM {KNOWLEDGE_DOCUMENTS_TABLE}
        WHERE user_id = :user_id AND original_filename = :original_filename
          AND deleted_at IS NULL
        ORDER BY version_no DESC, created_at DESC, id DESC
        LIMIT 1
        """,
        {"user_id": user_id, "original_filename": original_filename},
        conn=conn,
    )
    return _from_row(row) if row else None


def list_documents(
    user_id: str,
    status: KnowledgeDocumentStatus | str | None = None,
    limit: int = 50,
    *,
    conn: Connection | None = None,
) -> list[KnowledgeDocumentRecord]:
    clauses = ["user_id = :user_id"]
    params: dict[str, object] = {"user_id": user_id, "limit": limit}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = _status_value(status)
    rows = _fetch_all(
        f"""
        SELECT {_COLUMNS} FROM {KNOWLEDGE_DOCUMENTS_TABLE}
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """,
        params,
        conn=conn,
    )
    return [_from_row(row) for row in rows]


def update_status(
    document_id: str,
    status: KnowledgeDocumentStatus | str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    expected_status: KnowledgeDocumentStatus | str | None = None,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    params: dict[str, object] = {
        "id": document_id,
        "status": _status_value(status),
        "error_code": error_code,
        "error_message": (error_message or "")[:512] if error_message else None,
        "updated_at": _now(),
    }
    where = "id = :id"
    if expected_status is not None:
        params["expected_status"] = _status_value(expected_status)
        where += " AND status = :expected_status"
    result = _execute(
        f"""
        UPDATE {KNOWLEDGE_DOCUMENTS_TABLE}
        SET status = :status, error_code = :error_code,
            error_message = :error_message, updated_at = :updated_at
        WHERE {where}
        """,
        params,
        conn=conn,
        write=True,
    )
    if result.rowcount != 1:
        return None
    return get_document(document_id, conn=conn)


def update_parse_result(
    document_id: str,
    *,
    text_sha256: str,
    page_count: int | None,
    parser_name: str,
    parser_version: str,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    return _update_fields(
        document_id,
        {
            "text_sha256": text_sha256,
            "page_count": page_count,
            "parser_name": parser_name,
            "parser_version": parser_version,
        },
        conn=conn,
    )


def update_chunk_count(
    document_id: str,
    chunk_count: int,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    return _update_fields(document_id, {"chunk_count": chunk_count}, conn=conn)


def soft_delete(
    document_id: str,
    *,
    conn: Connection | None = None,
) -> KnowledgeDocumentRecord | None:
    result = _execute(
        f"""
        UPDATE {KNOWLEDGE_DOCUMENTS_TABLE}
        SET deleted_at = :deleted_at, dedupe_key = NULL,
            status = :status, updated_at = :updated_at
        WHERE id = :id
        """,
        {
            "id": document_id,
            "deleted_at": _now(),
            "status": KnowledgeDocumentStatus.DELETED.value,
            "updated_at": _now(),
        },
        conn=conn,
        write=True,
    )
    if result.rowcount != 1:
        return None
    return get_document(document_id, conn=conn)


def list_non_terminal(
    limit: int = 100,
    *,
    conn: Connection | None = None,
) -> list[KnowledgeDocumentRecord]:
    statuses = tuple(status.value for status in NON_TERMINAL_STATUSES)
    placeholders = ", ".join(f":status_{index}" for index in range(len(statuses)))
    params = {f"status_{index}": status for index, status in enumerate(statuses)}
    params["limit"] = limit
    rows = _fetch_all(
        f"""
        SELECT {_COLUMNS} FROM {KNOWLEDGE_DOCUMENTS_TABLE}
        WHERE status IN ({placeholders})
        ORDER BY updated_at ASC, id ASC
        LIMIT :limit
        """,
        params,
        conn=conn,
    )
    return [_from_row(row) for row in rows]


def _get_active_hash(
    column: str,
    user_id: str,
    value: str,
    *,
    conn: Connection | None,
) -> KnowledgeDocumentRecord | None:
    row = _fetch_one(
        f"""
        SELECT {_COLUMNS} FROM {KNOWLEDGE_DOCUMENTS_TABLE}
        WHERE user_id = :user_id AND {column} = :value AND deleted_at IS NULL
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        {"user_id": user_id, "value": value},
        conn=conn,
    )
    return _from_row(row) if row else None


def _update_fields(
    document_id: str,
    fields: dict[str, object],
    *,
    conn: Connection | None,
) -> KnowledgeDocumentRecord | None:
    values = dict(fields)
    values["id"] = document_id
    values["updated_at"] = _now()
    assignments = ", ".join(
        f"{key} = :{key}" for key in values if key != "id"
    )
    result = _execute(
        f"UPDATE {KNOWLEDGE_DOCUMENTS_TABLE} SET {assignments} WHERE id = :id",
        values,
        conn=conn,
        write=True,
    )
    if result.rowcount != 1:
        return None
    return get_document(document_id, conn=conn)


def _execute(
    sql: str,
    params: dict[str, object],
    *,
    conn: Connection | None,
    write: bool,
):
    if conn is not None:
        return conn.execute(text(sql), params)
    context = get_engine().begin() if write else get_engine().connect()
    with context as connection:
        return connection.execute(text(sql), params)


def _fetch_one(sql: str, params: dict[str, object], *, conn: Connection | None):
    result = _execute(sql, params, conn=conn, write=False)
    return result.mappings().fetchone()


def _fetch_all(sql: str, params: dict[str, object], *, conn: Connection | None):
    result = _execute(sql, params, conn=conn, write=False)
    return result.mappings().fetchall()


def _params(record: KnowledgeDocumentRecord) -> dict[str, object]:
    values = {column: getattr(record, column) for column in _COLUMN_NAMES}
    values["status"] = record.status.value
    return values


def _from_row(row) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        **{column: row[column] for column in _COLUMN_NAMES}
    )


def _status_value(status: KnowledgeDocumentStatus | str) -> str:
    return KnowledgeDocumentStatus(status).value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
