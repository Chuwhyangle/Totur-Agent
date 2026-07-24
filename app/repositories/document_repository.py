"""Document metadata database operations."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.database import get_connection, initialize_database
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    DOCUMENTS_TABLE,
    DocumentPurgeNotAllowedError,
    DocumentRecord,
    DocumentScope,
    DocumentStatus,
    InvalidDocumentRecord,
    InvalidDocumentStatusTransition,
    validate_document_status_transition,
)


class DocumentRepositoryError(RuntimeError):
    """Base exception for document repository operations."""


class DocumentSessionNotFoundError(DocumentRepositoryError):
    """The requested attachment session does not exist."""


class DocumentOwnershipError(DocumentRepositoryError):
    """The requested session is not owned by the supplied user."""


_ACTIVE_ATTACHMENT_STATUSES = (
    DocumentStatus.UPLOADED.value,
    DocumentStatus.PARSING.value,
    DocumentStatus.READY.value,
    DocumentStatus.PARTIAL.value,
    DocumentStatus.FAILED.value,
)
_ACTIVE_STATUS_PLACEHOLDERS = ", ".join(
    "?" for _ in _ACTIVE_ATTACHMENT_STATUSES
)
_RETRIEVABLE_ATTACHMENT_STATUSES = (
    DocumentStatus.READY.value,
    DocumentStatus.PARTIAL.value,
)
_RETRIEVABLE_STATUS_PLACEHOLDERS = ", ".join(
    "?" for _ in _RETRIEVABLE_ATTACHMENT_STATUSES
)


_DOCUMENT_COLUMNS = """
    id,
    scope,
    user_id,
    session_id,
    message_id,
    original_filename,
    mime_type,
    size_bytes,
    storage_path,
    parsed_path,
    content_hash,
    status,
    parser_name,
    parser_version,
    page_count,
    error_code,
    error_message,
    created_at,
    updated_at,
    expires_at
"""


def create_attachment_document(
    user_id: str,
    session_id: int,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    storage_path: str,
    expires_at: datetime | str,
    message_id: int | None = None,
    content_hash: str | None = None,
) -> DocumentRecord:
    """Create ATTACHMENT metadata after checking session ownership."""

    if not user_id or not user_id.strip():
        raise InvalidDocumentRecord("user_id must not be empty")
    if not original_filename or not original_filename.strip():
        raise InvalidDocumentRecord("original_filename must not be empty")
    if not mime_type or not mime_type.strip():
        raise InvalidDocumentRecord("mime_type must not be empty")
    if size_bytes < 0:
        raise InvalidDocumentRecord("size_bytes must not be negative")
    if not storage_path or not storage_path.strip():
        raise InvalidDocumentRecord("storage_path must not be empty")

    initialize_database()
    document_id = str(uuid4())
    now = _utc_now()
    normalized_expires_at = _normalize_utc_iso(expires_at, "expires_at")
    if datetime.fromisoformat(normalized_expires_at) <= datetime.fromisoformat(now):
        raise InvalidDocumentRecord(
            "expires_at must be strictly later than created_at"
        )
    insert_sql = f"""
    INSERT INTO {DOCUMENTS_TABLE} (
        id,
        scope,
        user_id,
        session_id,
        message_id,
        original_filename,
        mime_type,
        size_bytes,
        storage_path,
        parsed_path,
        content_hash,
        status,
        parser_name,
        parser_version,
        page_count,
        error_code,
        error_message,
        created_at,
        updated_at,
        expires_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    connection = get_connection()

    try:
        session = connection.execute(
            f"SELECT user_id FROM {CHAT_SESSIONS_TABLE} WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise DocumentSessionNotFoundError(
                f"Chat session {session_id} does not exist"
            )
        if session["user_id"] != user_id:
            raise DocumentOwnershipError(
                f"Chat session {session_id} is not owned by user {user_id}"
            )

        values = (
            document_id,
            DocumentScope.ATTACHMENT.value,
            user_id,
            session_id,
            message_id,
            original_filename,
            mime_type,
            size_bytes,
            storage_path,
            None,
            content_hash,
            DocumentStatus.UPLOADED.value,
            None,
            None,
            None,
            None,
            None,
            now,
            now,
            normalized_expires_at,
        )
        connection.execute(insert_sql, values)
        row = connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENTS_TABLE} WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Created document record could not be reloaded")

        created = _record_from_row(row)
        connection.commit()
        return created
    finally:
        connection.close()


def get_document(document_id: str) -> DocumentRecord | None:
    """Get document metadata by id for internal lifecycle operations."""

    initialize_database()
    connection = get_connection()

    try:
        row = connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENTS_TABLE} WHERE id = ?",
            (document_id,),
        ).fetchone()
        return _record_from_row(row) if row is not None else None
    finally:
        connection.close()


def get_owned_attachment(
    document_id: str,
    user_id: str,
    session_id: int,
) -> DocumentRecord | None:
    """Return an attachment only when id, scope, user, and session all match."""

    initialize_database()
    connection = get_connection()

    try:
        row = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE id = ?
                AND scope = ?
                AND user_id = ?
                AND session_id = ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            """,
            (
                document_id,
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                *_ACTIVE_ATTACHMENT_STATUSES,
            ),
        ).fetchone()
        return _record_from_row(row) if row is not None else None
    finally:
        connection.close()


def list_session_attachments(
    user_id: str,
    session_id: int,
) -> list[DocumentRecord]:
    """List only attachments owned by one user in one session."""

    initialize_database()
    connection = get_connection()

    try:
        rows = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE scope = ?
                AND user_id = ?
                AND session_id = ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            ORDER BY created_at DESC, id DESC
            """,
            (
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                *_ACTIVE_ATTACHMENT_STATUSES,
            ),
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def get_accessible_attachment(
    document_id: str,
    user_id: str,
    session_id: int,
    now: datetime | str,
) -> DocumentRecord | None:
    """Return one unexpired attachment visible to its owning session."""

    initialize_database()
    normalized_now = _normalize_utc_iso(now, "now")
    connection = get_connection()

    try:
        row = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE id = ?
                AND scope = ?
                AND user_id = ?
                AND session_id = ?
                AND expires_at > ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            """,
            (
                document_id,
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                normalized_now,
                *_ACTIVE_ATTACHMENT_STATUSES,
            ),
        ).fetchone()
        return _record_from_row(row) if row is not None else None
    finally:
        connection.close()


def list_accessible_session_attachments(
    user_id: str,
    session_id: int,
    now: datetime | str,
) -> list[DocumentRecord]:
    """List unexpired active attachments for one user and session."""

    initialize_database()
    normalized_now = _normalize_utc_iso(now, "now")
    connection = get_connection()

    try:
        rows = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE scope = ?
                AND user_id = ?
                AND session_id = ?
                AND expires_at > ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            ORDER BY created_at DESC, id DESC
            """,
            (
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                normalized_now,
                *_ACTIVE_ATTACHMENT_STATUSES,
            ),
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def count_accessible_session_attachments(
    user_id: str,
    session_id: int,
    now: datetime | str,
) -> int:
    """Count unexpired active attachments for upload quota checks."""

    initialize_database()
    normalized_now = _normalize_utc_iso(now, "now")
    connection = get_connection()

    try:
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS attachment_count
            FROM {DOCUMENTS_TABLE}
            WHERE scope = ?
                AND user_id = ?
                AND session_id = ?
                AND expires_at > ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            """,
            (
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                normalized_now,
                *_ACTIVE_ATTACHMENT_STATUSES,
            ),
        ).fetchone()
        return int(row["attachment_count"])
    finally:
        connection.close()


def get_retrievable_attachment(
    document_id: str,
    user_id: str,
    session_id: int,
    now: datetime | str,
) -> DocumentRecord | None:
    """Return only unexpired READY/PARTIAL attachment parser results."""

    initialize_database()
    normalized_now = _normalize_utc_iso(now, "now")
    connection = get_connection()

    try:
        row = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE id = ?
                AND scope = ?
                AND user_id = ?
                AND session_id = ?
                AND expires_at > ?
                AND status IN ({_RETRIEVABLE_STATUS_PLACEHOLDERS})
            """,
            (
                document_id,
                DocumentScope.ATTACHMENT.value,
                user_id,
                session_id,
                normalized_now,
                *_RETRIEVABLE_ATTACHMENT_STATUSES,
            ),
        ).fetchone()
        return _record_from_row(row) if row is not None else None
    finally:
        connection.close()


def update_document_status(
    document_id: str,
    status: DocumentStatus | str,
    *,
    parsed_path: str | None = None,
    content_hash: str | None = None,
    parser_name: str | None = None,
    parser_version: str | None = None,
    page_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> DocumentRecord | None:
    """Apply one validated lifecycle transition and optional parser metadata."""

    try:
        target_status = DocumentStatus(status)
    except ValueError as exc:
        raise InvalidDocumentRecord(f"Unknown document status: {status}") from exc

    if page_count is not None and page_count < 0:
        raise InvalidDocumentRecord("page_count must not be negative")
    if error_code is not None and not error_code.strip():
        raise InvalidDocumentRecord("error_code must not be blank")
    if target_status is DocumentStatus.FAILED and error_code is None:
        raise InvalidDocumentRecord(
            "A transition to FAILED requires a stable error_code"
        )

    parser_metadata = {
        "parsed_path": parsed_path,
        "content_hash": content_hash,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "page_count": page_count,
        "error_code": error_code,
        "error_message": error_message,
    }
    metadata_statuses = {
        DocumentStatus.PARSING,
        DocumentStatus.READY,
        DocumentStatus.PARTIAL,
        DocumentStatus.FAILED,
    }
    if target_status not in metadata_statuses and any(
        value is not None for value in parser_metadata.values()
    ):
        raise InvalidDocumentRecord(
            f"Parser metadata cannot be written while entering "
            f"{target_status.value}"
        )
    if target_status is DocumentStatus.PARSING and any(
        value is not None
        for value in (parsed_path, page_count, error_code, error_message)
    ):
        raise InvalidDocumentRecord(
            "PARSING resets parsed output and errors; only parser identity, "
            "version, and content_hash may be supplied"
        )

    initialize_database()
    connection = get_connection()

    try:
        row = connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENTS_TABLE} WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return None

        current = _record_from_row(row)
        validate_document_status_transition(current.status, target_status)

        updates: dict[str, object] = {
            "status": target_status.value,
            "updated_at": _utc_now(),
        }
        for column in ("content_hash", "parser_name", "parser_version"):
            value = parser_metadata[column]
            if value is not None:
                updates[column] = value

        if target_status is DocumentStatus.PARSING:
            updates["parsed_path"] = None
            updates["page_count"] = None
            updates["error_code"] = None
            updates["error_message"] = None
        else:
            if parsed_path is not None:
                updates["parsed_path"] = parsed_path
            if page_count is not None:
                updates["page_count"] = page_count

            effective_parsed_path = (
                parsed_path if parsed_path is not None else current.parsed_path
            )
            effective_page_count = (
                page_count if page_count is not None else current.page_count
            )
            effective_error_code = (
                error_code if error_code is not None else current.error_code
            )

            if target_status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
                _validate_usable_parse_result(
                    target_status,
                    effective_parsed_path,
                    effective_page_count,
                    effective_error_code,
                )

            if target_status is DocumentStatus.READY:
                updates["error_code"] = None
                updates["error_message"] = None
            elif target_status is DocumentStatus.FAILED:
                updates["error_code"] = error_code.strip() if error_code else None
                updates["error_message"] = error_message
            else:
                if error_code is not None:
                    updates["error_code"] = error_code.strip()
                if error_message is not None:
                    updates["error_message"] = error_message

        assignments = ", ".join(f"{column} = ?" for column in updates)
        values = [*updates.values(), document_id, current.status.value]
        cursor = connection.execute(
            f"""
            UPDATE {DOCUMENTS_TABLE}
            SET {assignments}
            WHERE id = ? AND status = ?
            """,
            values,
        )
        if cursor.rowcount != 1:
            raise DocumentRepositoryError(
                "Document status changed concurrently; retry the transition"
            )

        updated_row = connection.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM {DOCUMENTS_TABLE} WHERE id = ?",
            (document_id,),
        ).fetchone()
        if updated_row is None:
            raise RuntimeError("Updated document record could not be reloaded")

        updated = _record_from_row(updated_row)
        connection.commit()
        return updated
    finally:
        connection.close()


def list_expired_attachments(
    now: datetime | str,
    limit: int,
) -> list[DocumentRecord]:
    """List expired attachments in expiration order for future cleanup."""

    if limit < 0:
        raise ValueError("limit must not be negative")
    if limit == 0:
        return []

    initialize_database()
    normalized_now = _normalize_utc_iso(now, "now")
    connection = get_connection()

    try:
        rows = connection.execute(
            f"""
            SELECT {_DOCUMENT_COLUMNS}
            FROM {DOCUMENTS_TABLE}
            WHERE scope = ?
                AND expires_at IS NOT NULL
                AND expires_at <= ?
                AND status IN ({_ACTIVE_STATUS_PLACEHOLDERS})
            ORDER BY expires_at ASC, created_at ASC, id ASC
            LIMIT ?
            """,
            (
                DocumentScope.ATTACHMENT.value,
                normalized_now,
                *_ACTIVE_ATTACHMENT_STATUSES,
                limit,
            ),
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def delete_document_record(document_id: str) -> bool:
    """Purge SQLite metadata only after lifecycle cleanup reaches DELETED."""

    initialize_database()
    connection = get_connection()

    try:
        row = connection.execute(
            f"SELECT status FROM {DOCUMENTS_TABLE} WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        if row["status"] != DocumentStatus.DELETED.value:
            raise DocumentPurgeNotAllowedError(
                f"Document {document_id} cannot be purged from "
                f"{row['status']}; DELETED is required"
            )

        cursor = connection.execute(
            f"""
            DELETE FROM {DOCUMENTS_TABLE}
            WHERE id = ? AND status = ?
            """,
            (document_id, DocumentStatus.DELETED.value),
        )
        if cursor.rowcount != 1:
            raise DocumentRepositoryError(
                "Document status changed concurrently; retry the purge"
            )
        connection.commit()
        return True
    finally:
        connection.close()


def _validate_usable_parse_result(
    status: DocumentStatus,
    parsed_path: str | None,
    page_count: int | None,
    error_code: str | None,
) -> None:
    if not parsed_path or not parsed_path.strip():
        raise InvalidDocumentRecord(
            f"{status.value} requires a non-empty parsed_path"
        )
    if page_count is None or page_count <= 0:
        raise InvalidDocumentRecord(
            f"{status.value} requires page_count > 0"
        )
    if status is DocumentStatus.PARTIAL and not (
        error_code and error_code.strip()
    ):
        raise InvalidDocumentRecord(
            "PARTIAL requires a stable error or warning code"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_utc_iso(value: datetime | str, field_name: str) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidDocumentRecord(
                f"{field_name} must be an ISO 8601 timestamp"
            ) from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise InvalidDocumentRecord(
            f"{field_name} must be a datetime or ISO 8601 timestamp"
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidDocumentRecord(f"{field_name} must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat()


def _record_from_row(row) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        scope=DocumentScope(row["scope"]),
        user_id=row["user_id"],
        session_id=row["session_id"],
        message_id=row["message_id"],
        original_filename=row["original_filename"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        storage_path=row["storage_path"],
        parsed_path=row["parsed_path"],
        content_hash=row["content_hash"],
        status=DocumentStatus(row["status"]),
        parser_name=row["parser_name"],
        parser_version=row["parser_version"],
        page_count=row["page_count"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )
