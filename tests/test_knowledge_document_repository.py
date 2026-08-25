"""Repository tests for knowledge document metadata."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import KnowledgeDocumentRecord, KnowledgeDocumentStatus
from app.repositories.knowledge_document_repository import (
    get_active_by_file_hash,
    get_active_by_text_hash,
    get_document,
    get_latest_by_filename,
    insert_uploaded,
    list_non_terminal,
    soft_delete,
    update_status,
)


def make_record(
    *,
    document_id: str | None = None,
    user_id: str = "alice",
    filename: str = "notes.md",
    file_sha256: str = "a" * 64,
    text_sha256: str | None = "b" * 64,
    version_no: int = 1,
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.UPLOADED,
) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        id=document_id or str(uuid4()),
        user_id=user_id,
        original_filename=filename,
        media_type="text/markdown",
        size_bytes=12,
        storage_key=f"knowledge_docs/{filename}",
        file_sha256=file_sha256,
        text_sha256=text_sha256,
        dedupe_key=file_sha256,
        version_no=version_no,
        status=status,
        page_count=None,
        chunk_count=None,
        parser_name=None,
        parser_version=None,
        error_code=None,
        error_message=None,
        created_at="2026-08-25T00:00:00+00:00",
        updated_at="2026-08-25T00:00:00+00:00",
    )


def test_insert_and_get():
    record = make_record()

    insert_uploaded(record)

    loaded = get_document(record.id)
    assert loaded == record
    assert loaded.status is KnowledgeDocumentStatus.UPLOADED


def test_duplicate_dedupe_key_raises_integrity_error():
    insert_uploaded(make_record())

    with pytest.raises(IntegrityError):
        insert_uploaded(make_record(document_id=str(uuid4())))


def test_soft_delete_releases_dedupe_key():
    original = make_record()
    insert_uploaded(original)

    deleted = soft_delete(original.id)
    replacement = make_record(document_id=str(uuid4()))
    insert_uploaded(replacement)

    assert deleted is not None
    assert deleted.status is KnowledgeDocumentStatus.DELETED
    assert deleted.dedupe_key is None
    assert get_document(replacement.id) is not None


def test_get_active_by_file_hash_excludes_deleted():
    record = make_record()
    insert_uploaded(record)
    soft_delete(record.id)

    assert get_active_by_file_hash(record.user_id, record.file_sha256) is None


def test_get_active_by_text_hash_excludes_deleted():
    record = make_record()
    insert_uploaded(record)
    soft_delete(record.id)

    assert get_active_by_text_hash(record.user_id, record.text_sha256 or "") is None


def test_get_latest_by_filename_returns_highest_version():
    first = make_record(file_sha256="1" * 64, version_no=1)
    second = make_record(file_sha256="2" * 64, version_no=2)
    insert_uploaded(first)
    insert_uploaded(second)

    latest = get_latest_by_filename("alice", "notes.md")

    assert latest is not None
    assert latest.id == second.id
    assert latest.version_no == 2


def test_update_status_cas_rejects_stale_expected():
    record = make_record()
    insert_uploaded(record)
    assert update_status(
        record.id,
        KnowledgeDocumentStatus.PARSING,
        expected_status=KnowledgeDocumentStatus.UPLOADED,
    ) is not None

    stale = update_status(
        record.id,
        KnowledgeDocumentStatus.CHUNKING,
        expected_status=KnowledgeDocumentStatus.UPLOADED,
    )

    assert stale is None
    current = get_document(record.id)
    assert current is not None
    assert current.status is KnowledgeDocumentStatus.PARSING


def test_list_non_terminal_excludes_ready_failed_deleted():
    non_terminal = make_record(status=KnowledgeDocumentStatus.UPLOADED)
    ready = make_record(
        document_id=str(uuid4()),
        file_sha256="c" * 64,
        status=KnowledgeDocumentStatus.READY,
    )
    failed = make_record(
        document_id=str(uuid4()),
        file_sha256="d" * 64,
        status=KnowledgeDocumentStatus.FAILED,
    )
    deleted = make_record(
        document_id=str(uuid4()),
        file_sha256="e" * 64,
        status=KnowledgeDocumentStatus.DELETED,
    )
    for record in (non_terminal, ready, failed, deleted):
        insert_uploaded(record)

    records = list_non_terminal()

    assert [record.id for record in records] == [non_terminal.id]
