"""Unit tests for conversation attachment document metadata."""

import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db import database
import app.repositories.document_repository as document_repository
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DOCUMENTS_TABLE,
    DocumentPurgeNotAllowedError,
    DocumentScope,
    DocumentStatus,
    InvalidDocumentRecord,
    InvalidDocumentStatusTransition,
)
from app.repositories.document_repository import (
    DocumentOwnershipError,
    DocumentSessionNotFoundError,
    count_accessible_session_attachments,
    create_attachment_document,
    delete_document_record,
    get_accessible_attachment,
    get_attachment_for_cleanup,
    get_document,
    get_owned_attachment,
    get_retrievable_attachment,
    list_accessible_session_attachments,
    list_expired_attachments,
    list_session_attachments,
    list_stale_cleanup_attachments,
    list_stale_deleting_attachments,
    list_stale_parsing_attachments,
    list_stale_processing_attachments,
    update_document_status,
)
from app.repositories.session_repository import create_session, list_sessions


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def open_engine_db(tmp_path):
    """打开当前测试的底层 SQLite 库（A1 后库文件固定为 tutor_agent.db）。"""

    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_attachment(
    user_id,
    session_id,
    filename="notes.pdf",
    expires_at="2030-01-01T00:00:00+00:00",
):
    return create_attachment_document(
        user_id=user_id,
        session_id=session_id,
        message_id=42,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=512,
        storage_path=f"/documents/{filename}",
        content_hash="sha256:example",
        expires_at=expires_at,
    )


def test_initialize_database_creates_documents_table_and_indexes(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    database.initialize_database()

    connection = open_engine_db(tmp_path)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({DOCUMENTS_TABLE})")
        }
        indexes = {
            row["name"]
            for row in connection.execute(f"PRAGMA index_list({DOCUMENTS_TABLE})")
        }
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({DOCUMENTS_TABLE})"
        ).fetchall()
    finally:
        connection.close()

    assert {
        "id",
        "scope",
        "user_id",
        "session_id",
        "message_id",
        "original_filename",
        "mime_type",
        "size_bytes",
        "storage_path",
        "parsed_path",
        "content_hash",
        "status",
        "parser_name",
        "parser_version",
        "page_count",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
        "expires_at",
    } == columns
    assert {
        "idx_documents_user_session",
        "idx_documents_status",
        "idx_documents_expires_at",
    }.issubset(indexes)
    assert any(
        row["table"] == CHAT_SESSIONS_TABLE
        and row["from"] == "session_id"
        and row["on_delete"] == "RESTRICT"
        for row in foreign_keys
    )


def test_initialize_database_is_idempotent(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    database.initialize_database()
    database.initialize_database()

    connection = open_engine_db(tmp_path)
    try:
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            (DOCUMENTS_TABLE,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert table_count == 1


def test_create_attachment_document_stores_expected_fields(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice", title="Document chat")

    created = create_attachment_document(
        user_id="alice",
        session_id=session.id,
        message_id=7,
        original_filename="resume.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        storage_path="/documents/resume.pdf",
        content_hash="sha256:resume",
        expires_at="2030-01-02T08:00:00+08:00",
    )
    loaded = get_document(created.id)

    assert loaded == created
    assert created.scope is DocumentScope.ATTACHMENT
    assert created.status is DocumentStatus.UPLOADED
    assert created.user_id == "alice"
    assert created.session_id == session.id
    assert created.message_id == 7
    assert created.original_filename == "resume.pdf"
    assert created.mime_type == "application/pdf"
    assert created.size_bytes == 2048
    assert created.storage_path == "/documents/resume.pdf"
    assert created.content_hash == "sha256:resume"
    assert created.parsed_path is None
    assert created.expires_at == "2030-01-02T00:00:00+00:00"
    assert created.created_at.endswith("+00:00")
    assert created.updated_at.endswith("+00:00")


def test_attachment_document_ids_are_random_uuid_values(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")

    first = create_attachment("alice", session.id, filename="first.pdf")
    second = create_attachment("alice", session.id, filename="second.pdf")

    assert first.id != second.id
    assert str(UUID(first.id)) == first.id
    assert str(UUID(second.id)) == second.id


def test_create_attachment_checks_session_exists_and_is_owned(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    bob_session = create_session("bob")

    with pytest.raises(DocumentSessionNotFoundError):
        create_attachment("alice", 9999)
    with pytest.raises(DocumentOwnershipError):
        create_attachment("alice", bob_session.id)

    assert list_session_attachments("alice", bob_session.id) == []


def test_owned_attachment_is_readable_by_same_user_and_session(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)

    loaded = get_owned_attachment(document.id, "alice", session.id)

    assert loaded == document


def test_owned_attachment_is_hidden_from_different_user(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)

    assert get_owned_attachment(document.id, "bob", session.id) is None


def test_owned_attachment_is_hidden_from_different_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    first_session = create_session("alice", title="First")
    second_session = create_session("alice", title="Second")
    document = create_attachment("alice", first_session.id)

    assert get_owned_attachment(document.id, "alice", second_session.id) is None


def test_list_session_attachments_isolates_user_and_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    alice_first = create_session("alice", title="First")
    alice_second = create_session("alice", title="Second")
    bob_session = create_session("bob")
    first = create_attachment("alice", alice_first.id, filename="first.pdf")
    second = create_attachment("alice", alice_first.id, filename="second.pdf")
    create_attachment("alice", alice_second.id, filename="other-session.pdf")
    create_attachment("bob", bob_session.id, filename="other-user.pdf")

    records = list_session_attachments("alice", alice_first.id)

    assert {record.id for record in records} == {first.id, second.id}
    assert all(record.user_id == "alice" for record in records)
    assert all(record.session_id == alice_first.id for record in records)


def test_all_allowed_document_status_transitions_succeed(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")

    uploaded_cleanup = create_attachment(
        "alice",
        session.id,
        filename="uploaded-cleanup.pdf",
    )
    assert update_document_status(
        uploaded_cleanup.id,
        DocumentStatus.DELETING,
    ).status is DocumentStatus.DELETING

    parsing_cleanup = create_attachment(
        "alice",
        session.id,
        filename="parsing-cleanup.pdf",
    )
    update_document_status(parsing_cleanup.id, DocumentStatus.PARSING)
    assert update_document_status(
        parsing_cleanup.id,
        DocumentStatus.DELETING,
    ).status is DocumentStatus.DELETING

    ready_document = create_attachment("alice", session.id, filename="ready.pdf")
    assert update_document_status(
        ready_document.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    ).status is DocumentStatus.PARSING
    assert update_document_status(
        ready_document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/ready.txt",
        page_count=2,
    ).status is DocumentStatus.INDEXING
    assert update_document_status(
        ready_document.id,
        DocumentStatus.READY,
    ).status is DocumentStatus.READY
    assert update_document_status(
        ready_document.id,
        DocumentStatus.DELETING,
    ).status is DocumentStatus.DELETING
    assert update_document_status(
        ready_document.id,
        DocumentStatus.DELETED,
    ).status is DocumentStatus.DELETED

    partial_document = create_attachment(
        "alice",
        session.id,
        filename="partial.pdf",
    )
    update_document_status(
        partial_document.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    assert update_document_status(
        partial_document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/partial.txt",
        page_count=1,
    ).status is DocumentStatus.INDEXING
    assert update_document_status(
        partial_document.id,
        DocumentStatus.PARTIAL,
        error_code="PAGE_SKIPPED",
    ).status is DocumentStatus.PARTIAL
    assert update_document_status(
        partial_document.id,
        DocumentStatus.DELETING,
    ).status is DocumentStatus.DELETING

    failed_document = create_attachment(
        "alice",
        session.id,
        filename="failed.pdf",
    )
    update_document_status(failed_document.id, DocumentStatus.PARSING)
    assert update_document_status(
        failed_document.id,
        DocumentStatus.FAILED,
        error_code="PARSER_CRASH",
    ).status is DocumentStatus.FAILED
    assert update_document_status(
        failed_document.id,
        DocumentStatus.DELETING,
    ).status is DocumentStatus.DELETING


def test_illegal_status_transition_raises_and_leaves_database_unchanged(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)

    with pytest.raises(InvalidDocumentStatusTransition, match="UPLOADED.*INDEXING"):
        update_document_status(document.id, DocumentStatus.INDEXING)

    unchanged = get_document(document.id)
    assert unchanged.status is DocumentStatus.UPLOADED
    assert unchanged.updated_at == document.updated_at


def test_failed_status_requires_and_persists_stable_error_code(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)

    with pytest.raises(InvalidDocumentRecord, match="error_code"):
        update_document_status(document.id, DocumentStatus.FAILED)
    assert get_document(document.id).status is DocumentStatus.PARSING

    failed = update_document_status(
        document.id,
        DocumentStatus.FAILED,
        error_code="UNSUPPORTED_FORMAT",
        error_message="The parser rejected this file.",
    )

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "UNSUPPORTED_FORMAT"
    assert failed.error_message == "The parser rejected this file."


def test_failed_document_can_retry_and_continue_to_ready(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)
    update_document_status(
        document.id,
        DocumentStatus.FAILED,
        parsed_path="parsed/stale.txt",
        page_count=2,
        error_code="TEMPORARY_IO_ERROR",
        error_message="Stale failure details.",
    )

    parsing = update_document_status(
        document.id,
        DocumentStatus.PARSING,
        parser_name="retry-parser",
        parser_version="2.0",
    )
    indexing = update_document_status(
        document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/retry.txt",
        page_count=3,
    )
    ready = update_document_status(document.id, DocumentStatus.READY)

    assert parsing.status is DocumentStatus.PARSING
    assert parsing.parsed_path is None
    assert parsing.page_count is None
    assert parsing.error_code is None
    assert parsing.error_message is None
    assert ready.status is DocumentStatus.READY
    assert ready.parser_name == "retry-parser"
    assert ready.parser_version == "2.0"
    assert ready.parsed_path == "parsed/retry.txt"
    assert ready.page_count == 3


def test_ready_clears_errors_from_previous_failed_attempt(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)
    update_document_status(
        document.id,
        DocumentStatus.FAILED,
        error_code="PARSER_TIMEOUT",
        error_message="Timed out.",
    )
    update_document_status(
        document.id,
        DocumentStatus.PARSING,
        parser_name="retry-parser",
        parser_version="2.0",
    )
    indexing = update_document_status(
        document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/ready-after-retry.txt",
        page_count=1,
    )
    ready = update_document_status(document.id, DocumentStatus.READY)

    assert indexing.error_code is None
    assert ready.error_code is None
    assert ready.error_message is None


def test_expired_query_returns_only_attachments_sorted_by_expiration(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    first = create_attachment(
        "alice",
        session.id,
        filename="first-expired.pdf",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    second = create_attachment(
        "alice",
        session.id,
        filename="second-expired.pdf",
        expires_at="2030-01-02T00:00:00+00:00",
    )
    create_attachment(
        "alice",
        session.id,
        filename="not-expired.pdf",
        expires_at="2030-01-04T00:00:00+00:00",
    )

    connection = open_engine_db(tmp_path)
    try:
        connection.execute(
            f"""
            INSERT INTO {DOCUMENTS_TABLE} (
                id, scope, user_id, session_id, message_id,
                original_filename, mime_type, size_bytes, storage_path,
                parsed_path, content_hash, status, parser_name, parser_version,
                page_count, error_code, error_message, created_at, updated_at,
                expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "expired-private",
                DocumentScope.PRIVATE.value,
                "alice",
                None,
                None,
                "private.pdf",
                "application/pdf",
                1,
                "/private/private.pdf",
                None,
                None,
                DocumentStatus.UPLOADED.value,
                None,
                None,
                None,
                None,
                None,
                "2029-01-01T00:00:00+00:00",
                "2029-01-01T00:00:00+00:00",
                "2030-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    expired = list_expired_attachments(
        "2030-01-03T00:00:00+00:00",
        limit=10,
    )

    assert [record.id for record in expired] == [first.id, second.id]
    assert all(record.scope is DocumentScope.ATTACHMENT for record in expired)


def test_deleting_and_deleted_documents_are_hidden_from_attachment_queries(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    deleting = create_attachment(
        "alice",
        session.id,
        filename="deleting.pdf",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    deleted = create_attachment(
        "alice",
        session.id,
        filename="deleted.pdf",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    visible = create_attachment(
        "alice",
        session.id,
        filename="visible.pdf",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    update_document_status(deleting.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETED)

    assert get_owned_attachment(deleting.id, "alice", session.id) is None
    assert get_owned_attachment(deleted.id, "alice", session.id) is None
    assert [
        record.id for record in list_session_attachments("alice", session.id)
    ] == [visible.id]
    assert [
        record.id
        for record in list_expired_attachments(
            "2030-02-01T00:00:00+00:00",
            limit=10,
        )
    ] == [visible.id]


def test_cleanup_query_returns_only_recoverable_attachment_states(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    active = create_attachment("alice", session.id, filename="active.pdf")
    deleting = create_attachment(
        "alice",
        session.id,
        filename="deleting.pdf",
    )
    deleted = create_attachment(
        "alice",
        session.id,
        filename="deleted.pdf",
    )
    update_document_status(deleting.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETED)

    assert get_attachment_for_cleanup(active.id) is None
    assert (
        get_attachment_for_cleanup(deleting.id).status
        is DocumentStatus.DELETING
    )
    assert (
        get_attachment_for_cleanup(deleted.id).status
        is DocumentStatus.DELETED
    )


def test_stale_deleting_query_filters_and_orders_candidates(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    first = create_attachment("alice", session.id, filename="first.pdf")
    second = create_attachment("alice", session.id, filename="second.pdf")
    recent = create_attachment("alice", session.id, filename="recent.pdf")
    deleted = create_attachment("alice", session.id, filename="deleted.pdf")
    for document in (first, second, recent, deleted):
        update_document_status(document.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETED)

    timestamps = {
        first.id: "2029-01-01T00:00:00+00:00",
        second.id: "2029-01-02T00:00:00+00:00",
        recent.id: "2031-01-01T00:00:00+00:00",
        deleted.id: "2028-01-01T00:00:00+00:00",
    }
    connection = open_engine_db(tmp_path)
    try:
        connection.executemany(
            f"UPDATE {DOCUMENTS_TABLE} SET updated_at = ? WHERE id = ?",
            [
                (updated_at, document_id)
                for document_id, updated_at in timestamps.items()
            ],
        )
        connection.commit()
    finally:
        connection.close()

    candidates = list_stale_deleting_attachments(
        "2030-01-01T00:00:00+00:00",
        limit=10,
    )

    assert [record.id for record in candidates] == [first.id, second.id]



def test_stale_cleanup_query_includes_deleting_and_deleted_with_stable_order(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    deleting = create_attachment("alice", session.id, filename="deleting.pdf")
    deleted = create_attachment("alice", session.id, filename="deleted.pdf")
    active = create_attachment("alice", session.id, filename="active.pdf")
    recent = create_attachment("alice", session.id, filename="recent.pdf")
    update_document_status(deleting.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETED)
    update_document_status(recent.id, DocumentStatus.DELETING)

    timestamps = {
        deleted.id: "2028-01-01T00:00:00+00:00",
        deleting.id: "2029-01-01T00:00:00+00:00",
        active.id: "2027-01-01T00:00:00+00:00",
        recent.id: "2031-01-01T00:00:00+00:00",
    }
    connection = open_engine_db(tmp_path)
    try:
        connection.executemany(
            f"UPDATE {DOCUMENTS_TABLE} SET updated_at = ? WHERE id = ?",
            [(timestamp, document_id) for document_id, timestamp in timestamps.items()],
        )
        connection.commit()
    finally:
        connection.close()

    candidates = list_stale_cleanup_attachments(
        "2030-01-01T00:00:00+00:00",
        limit=2,
    )

    assert [(record.id, record.status) for record in candidates] == [
        (deleted.id, DocumentStatus.DELETED),
        (deleting.id, DocumentStatus.DELETING),
    ]


def test_stale_parsing_query_filters_orders_and_limits(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    first = create_attachment("alice", session.id, filename="first.pdf")
    second = create_attachment("alice", session.id, filename="second.pdf")
    recent = create_attachment("alice", session.id, filename="recent.pdf")
    ready = create_attachment("alice", session.id, filename="ready.pdf")
    for document in (first, second, recent, ready):
        update_document_status(document.id, DocumentStatus.PARSING)
    update_document_status(
        ready.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/ready.json",
        page_count=1,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(ready.id, DocumentStatus.READY)

    timestamps = {
        first.id: "2028-01-01T00:00:00+00:00",
        second.id: "2029-01-01T00:00:00+00:00",
        recent.id: "2031-01-01T00:00:00+00:00",
        ready.id: "2027-01-01T00:00:00+00:00",
    }
    connection = open_engine_db(tmp_path)
    try:
        connection.executemany(
            f"UPDATE {DOCUMENTS_TABLE} SET updated_at = ? WHERE id = ?",
            [(timestamp, document_id) for document_id, timestamp in timestamps.items()],
        )
        connection.commit()
    finally:
        connection.close()

    candidates = list_stale_parsing_attachments(
        "2030-01-01T00:00:00+00:00",
        limit=1,
    )

    assert [record.id for record in candidates] == [first.id]

def test_indexing_requires_parsed_path_and_positive_page_count(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)

    with pytest.raises(InvalidDocumentRecord, match="parsed_path"):
        update_document_status(document.id, DocumentStatus.INDEXING)
    with pytest.raises(InvalidDocumentRecord, match="page_count > 0"):
        update_document_status(
            document.id,
            DocumentStatus.INDEXING,
            parsed_path="parsed/empty.txt",
            page_count=0,
        )

    assert get_document(document.id).status is DocumentStatus.PARSING


@pytest.mark.parametrize(
    "parsed_path",
    [
        "/absolute/result.json",
        "../escape.json",
        "parsed/../escape.json",
        r"C:\\secret\\result.json",
        " parsed/result.json",
    ],
)
def test_parsed_path_must_be_a_relative_storage_key(
    monkeypatch,
    tmp_path,
    parsed_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)

    with pytest.raises(InvalidDocumentRecord, match="relative storage key"):
        update_document_status(
            document.id,
            DocumentStatus.INDEXING,
            parsed_path=parsed_path,
            page_count=1,
        )

    assert get_document(document.id).status is DocumentStatus.PARSING


def test_partial_requires_usable_result_and_stable_warning_code(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(
        document.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/partial.txt",
        page_count=1,
    )

    with pytest.raises(InvalidDocumentRecord, match="stable error or warning code"):
        update_document_status(document.id, DocumentStatus.PARTIAL)

    partial = update_document_status(
        document.id,
        DocumentStatus.PARTIAL,
        error_code="ONE_PAGE_SKIPPED",
    )
    assert partial.status is DocumentStatus.PARTIAL


def test_initialize_database_migrates_cascade_fk_to_restrict(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    connection = open_engine_db(tmp_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            f"""
            CREATE TABLE {CHAT_SESSIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                persona_id TEXT NOT NULL DEFAULT 'tutor',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                subject TEXT
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {CHAT_SESSIONS_TABLE}
                (user_id, title, persona_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-user",
                "Legacy",
                "tutor",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        cascade_sql = database._create_documents_table_sql(
            DOCUMENTS_TABLE
        ).replace("ON DELETE RESTRICT", "ON DELETE CASCADE")
        connection.execute(cascade_sql)
        connection.execute(
            f"""
            INSERT INTO {DOCUMENTS_TABLE} (
                id, scope, user_id, session_id, message_id,
                original_filename, mime_type, size_bytes, storage_path,
                parsed_path, content_hash, status, parser_name, parser_version,
                page_count, error_code, error_message, created_at, updated_at,
                expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-document",
                DocumentScope.ATTACHMENT.value,
                "legacy-user",
                1,
                None,
                "legacy.pdf",
                "application/pdf",
                1,
                "/legacy/legacy.pdf",
                None,
                None,
                DocumentStatus.UPLOADED.value,
                None,
                None,
                None,
                None,
                None,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                "2030-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    database.initialize_database()
    database.initialize_database()

    connection = open_engine_db(tmp_path)
    try:
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({DOCUMENTS_TABLE})"
        ).fetchall()
        document = connection.execute(
            f"SELECT id, storage_path FROM {DOCUMENTS_TABLE} WHERE id = ?",
            ("legacy-document",),
        ).fetchone()
    finally:
        connection.close()

    assert any(
        row["table"] == CHAT_SESSIONS_TABLE
        and row["from"] == "session_id"
        and row["on_delete"] == "RESTRICT"
        for row in foreign_keys
    )
    assert document["id"] == "legacy-document"
    assert document["storage_path"] == "/legacy/legacy.pdf"


def test_session_delete_is_restricted_until_document_cleanup_finishes(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    stored_file = tmp_path / "stored.pdf"
    stored_file.write_bytes(b"document")
    document = create_attachment_document(
        user_id="alice",
        session_id=session.id,
        original_filename="stored.pdf",
        mime_type="application/pdf",
        size_bytes=stored_file.stat().st_size,
        storage_path=str(stored_file),
        expires_at="2030-01-01T00:00:00+00:00",
    )

    connection = open_engine_db(tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"DELETE FROM {CHAT_SESSIONS_TABLE} WHERE id = ?",
                (session.id,),
            )
        connection.rollback()
    finally:
        connection.close()

    retained = get_document(document.id)
    assert retained.storage_path == str(stored_file)
    assert stored_file.exists()

    update_document_status(document.id, DocumentStatus.DELETING)
    stored_file.unlink()
    update_document_status(document.id, DocumentStatus.DELETED)
    assert delete_document_record(document.id) is True

    connection = open_engine_db(tmp_path)
    try:
        connection.execute(
            f"DELETE FROM {CHAT_SESSIONS_TABLE} WHERE id = ?",
            (session.id,),
        )
        connection.commit()
    finally:
        connection.close()

    assert list_sessions("alice") == []


def test_non_deleted_document_cannot_be_purged(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)

    with pytest.raises(DocumentPurgeNotAllowedError, match="DELETED is required"):
        delete_document_record(document.id)

    assert get_document(document.id).status is DocumentStatus.UPLOADED


def test_delete_document_record_purges_only_deleted_metadata(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.DELETING)
    update_document_status(document.id, DocumentStatus.DELETED)

    assert delete_document_record(document.id) is True
    assert get_document(document.id) is None
    assert delete_document_record(document.id) is False


def test_legacy_database_initialization_preserves_existing_functionality(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    connection = open_engine_db(tmp_path)
    try:
        connection.execute(
            f"""
            CREATE TABLE {CONVERSATIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                reply_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {CONVERSATIONS_TABLE}
                (user_id, message, reply_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                "legacy-user",
                "legacy message",
                "{}",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    database.initialize_database()
    database.initialize_database()
    sessions = list_sessions("legacy-user")

    connection = open_engine_db(tmp_path)
    connection.row_factory = sqlite3.Row
    try:
        conversation = connection.execute(
            f"SELECT message, session_id FROM {CONVERSATIONS_TABLE}"
        ).fetchone()
        documents_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (DOCUMENTS_TABLE,),
        ).fetchone()
    finally:
        connection.close()

    assert len(sessions) == 1
    assert conversation["message"] == "legacy message"
    assert conversation["session_id"] == sessions[0].id
    assert documents_table["name"] == DOCUMENTS_TABLE



def test_create_attachment_rejects_expiry_at_or_before_created_at(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    fixed_created_at = "2030-01-01T00:00:00+00:00"
    monkeypatch.setattr(document_repository, "_utc_now", lambda: fixed_created_at)

    for expires_at in (
        fixed_created_at,
        "2029-12-31T23:59:59+00:00",
    ):
        with pytest.raises(InvalidDocumentRecord, match="strictly later"):
            create_attachment(
                "alice",
                session.id,
                filename="invalid-expiry.pdf",
                expires_at=expires_at,
            )

    assert list_session_attachments("alice", session.id) == []


def test_accessible_attachment_queries_enforce_ttl(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    document = create_attachment(
        "alice",
        session.id,
        expires_at=expires_at,
    )
    before_expiry = expires_at - timedelta(seconds=1)

    assert (
        get_accessible_attachment(
            document.id,
            "alice",
            session.id,
            before_expiry,
        ).id
        == document.id
    )
    assert [
        record.id
        for record in list_accessible_session_attachments(
            "alice",
            session.id,
            before_expiry,
        )
    ] == [document.id]
    assert (
        count_accessible_session_attachments(
            "alice",
            session.id,
            before_expiry,
        )
        == 1
    )

    assert (
        get_accessible_attachment(
            document.id,
            "alice",
            session.id,
            expires_at,
        )
        is None
    )
    assert (
        list_accessible_session_attachments(
            "alice",
            session.id,
            expires_at,
        )
        == []
    )
    assert (
        count_accessible_session_attachments(
            "alice",
            session.id,
            expires_at,
        )
        == 0
    )


def test_retrievable_query_allows_only_ready_and_partial(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    query_now = datetime.now(timezone.utc)
    expires_at = query_now + timedelta(hours=2)
    uploaded = create_attachment(
        "alice",
        session.id,
        filename="uploaded.pdf",
        expires_at=expires_at,
    )
    indexing = create_attachment(
        "alice",
        session.id,
        filename="indexing.pdf",
        expires_at=expires_at,
    )
    ready = create_attachment(
        "alice",
        session.id,
        filename="ready.pdf",
        expires_at=expires_at,
    )
    partial = create_attachment(
        "alice",
        session.id,
        filename="partial.pdf",
        expires_at=expires_at,
    )
    update_document_status(
        indexing.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        indexing.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/indexing.json",
        page_count=1,
    )
    update_document_status(ready.id, DocumentStatus.PARSING)
    update_document_status(
        ready.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/ready.json",
        page_count=2,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(ready.id, DocumentStatus.READY)
    update_document_status(partial.id, DocumentStatus.PARSING)
    update_document_status(
        partial.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/partial.json",
        page_count=1,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        partial.id,
        DocumentStatus.PARTIAL,
        error_code="PARTIAL_TEXT",
    )

    assert (
        get_retrievable_attachment(
            uploaded.id,
            "alice",
            session.id,
            query_now,
        )
        is None
    )
    assert (
        get_retrievable_attachment(
            indexing.id,
            "alice",
            session.id,
            query_now,
        )
        is None
    )
    assert (
        get_retrievable_attachment(
            ready.id,
            "alice",
            session.id,
            query_now,
        ).status
        is DocumentStatus.READY
    )
    assert (
        get_retrievable_attachment(
            partial.id,
            "alice",
            session.id,
            query_now,
        ).status
        is DocumentStatus.PARTIAL
    )
    assert (
        get_retrievable_attachment(
            ready.id,
            "bob",
            session.id,
            query_now,
        )
        is None
    )



def test_stale_processing_query_includes_parsing_and_indexing(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    parsing = create_attachment("alice", session.id, filename="parsing.pdf")
    indexing = create_attachment("alice", session.id, filename="indexing.pdf")
    ready = create_attachment("alice", session.id, filename="ready.pdf")
    update_document_status(parsing.id, DocumentStatus.PARSING)
    update_document_status(
        indexing.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        indexing.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/indexing.json",
        page_count=1,
    )
    update_document_status(
        ready.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        ready.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/ready.json",
        page_count=1,
    )
    update_document_status(ready.id, DocumentStatus.READY)

    connection = open_engine_db(tmp_path)
    try:
        connection.executemany(
            f"UPDATE {DOCUMENTS_TABLE} SET updated_at = ? WHERE id = ?",
            [
                ("2028-01-01T00:00:00+00:00", parsing.id),
                ("2029-01-01T00:00:00+00:00", indexing.id),
                ("2027-01-01T00:00:00+00:00", ready.id),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    records = list_stale_processing_attachments(
        "2030-01-01T00:00:00+00:00",
        limit=10,
    )

    assert [(record.id, record.status) for record in records] == [
        (parsing.id, DocumentStatus.PARSING),
        (indexing.id, DocumentStatus.INDEXING),
    ]


def test_initialize_database_migrates_legacy_ready_rows_for_reindex(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    connection = open_engine_db(tmp_path)
    try:
        connection.execute(
            f"""
            CREATE TABLE {CHAT_SESSIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                persona_id TEXT NOT NULL DEFAULT 'tutor',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                subject TEXT
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {CHAT_SESSIONS_TABLE}
                (id, user_id, title, persona_id, created_at, updated_at)
            VALUES (1, 'alice', 'Legacy', 'tutor', ?, ?)
            """,
            ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            f"""
            CREATE TABLE {DOCUMENTS_TABLE} (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK (scope IN ('INTERNAL', 'PRIVATE', 'ATTACHMENT')),
                user_id TEXT,
                session_id INTEGER REFERENCES {CHAT_SESSIONS_TABLE}(id) ON DELETE RESTRICT,
                message_id INTEGER,
                original_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                storage_path TEXT NOT NULL,
                parsed_path TEXT,
                content_hash TEXT,
                status TEXT NOT NULL CHECK (status IN (
                    'UPLOADED', 'PARSING', 'READY', 'PARTIAL',
                    'FAILED', 'DELETING', 'DELETED'
                )),
                parser_name TEXT,
                parser_version TEXT,
                page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                CHECK (
                    scope <> 'ATTACHMENT'
                    OR (user_id IS NOT NULL AND session_id IS NOT NULL AND expires_at IS NOT NULL)
                ),
                CHECK (status <> 'FAILED' OR error_code IS NOT NULL)
            )
            """
        )
        for document_id, status in (("legacy-ready", "READY"), ("legacy-partial", "PARTIAL")):
            connection.execute(
                f"""
                INSERT INTO {DOCUMENTS_TABLE} (
                    id, scope, user_id, session_id, original_filename, mime_type,
                    size_bytes, storage_path, parsed_path, status, parser_name,
                    parser_version, page_count, created_at, updated_at, expires_at,
                    error_code
                ) VALUES (?, 'ATTACHMENT', 'alice', 1, ?, 'application/pdf',
                    100, ?, ?, ?, 'pymupdf', '1.0', 2, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    f"{document_id}.pdf",
                    f"original/{document_id}.pdf",
                    f"parsed/{document_id}.json",
                    status,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    "2030-01-01T00:00:00+00:00",
                    "OLD_PARTIAL_WARNING" if status == "PARTIAL" else None,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    database.initialize_database()
    database.initialize_database()

    ready = get_document("legacy-ready")
    partial = get_document("legacy-partial")
    connection = open_engine_db(tmp_path)
    try:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (DOCUMENTS_TABLE,),
        ).fetchone()["sql"]
        indexes = {
            row["name"] for row in connection.execute(f"PRAGMA index_list({DOCUMENTS_TABLE})")
        }
    finally:
        connection.close()

    for record in (ready, partial):
        assert record.status is DocumentStatus.FAILED
        assert record.error_code == "REINDEX_REQUIRED"
        assert record.error_message == "Existing parsed attachment requires indexing"
        assert record.storage_path == f"original/{record.id}.pdf"
        assert record.parsed_path == f"parsed/{record.id}.json"
    assert "'INDEXING'" in table_sql
    assert {
        "idx_documents_user_session",
        "idx_documents_status",
        "idx_documents_expires_at",
    }.issubset(indexes)


def test_expected_status_rejects_stale_transition(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = create_attachment("alice", session.id)
    update_document_status(document.id, DocumentStatus.PARSING)

    with pytest.raises(
        document_repository.DocumentRepositoryError,
        match="changed concurrently",
    ):
        update_document_status(
            document.id,
            DocumentStatus.FAILED,
            expected_status=DocumentStatus.UPLOADED,
            error_code="STALE_WORKER",
            error_message="A stale worker must not overwrite the current state",
        )

    current = get_document(document.id)
    assert current is not None
    assert current.status is DocumentStatus.PARSING
    assert current.error_code is None
