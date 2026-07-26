"""Race-condition regressions for attachment retry and startup recovery."""

from datetime import datetime, timezone

import pytest

from app.db import database
from app.db.models import DocumentStatus
import app.repositories.document_repository as document_repository
from app.repositories.document_repository import (
    create_attachment_document,
    get_document,
    update_document_status,
)
from app.repositories.session_repository import create_session
from app.services.documents.attachment_recovery_service import (
    AttachmentRecoveryService,
)
from app.services.documents.attachment_retry_service import (
    AttachmentAlreadyProcessing,
    AttachmentRetryService,
)
from app.services.documents.settings import TemporaryDocumentSettings


class RecordingParsedStorage:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []

    def delete(self, storage_key: str) -> None:
        self.deleted_paths.append(storage_key)


def _use_temp_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "retry-recovery.db")


def _create_attachment(session_id: int, filename: str = "notes.pdf"):
    return create_attachment_document(
        user_id="alice",
        session_id=session_id,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=128,
        storage_path=f"stored/{filename}",
        expires_at="2030-01-01T00:00:00+00:00",
    )


def _settings(tmp_path, **overrides) -> TemporaryDocumentSettings:
    values = {
        "root_path": tmp_path / "attachments",
        "recovery_batch_size": 1,
    }
    values.update(overrides)
    return TemporaryDocumentSettings(**values)


def test_retry_cas_loser_does_not_delete_parsed_json(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = _create_attachment(session.id)
    update_document_status(document.id, DocumentStatus.PARSING)
    update_document_status(
        document.id,
        DocumentStatus.FAILED,
        parsed_path="parsed/stale.json",
        error_code="TRANSIENT_FAILURE",
        error_message="retryable",
    )
    storage = RecordingParsedStorage()
    service = AttachmentRetryService(
        _settings(tmp_path),
        parsed_storage=storage,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
    )
    real_update = document_repository.update_document_status

    def competing_update(document_id, status, **kwargs):
        if DocumentStatus(status) is DocumentStatus.PARSING:
            real_update(document_id, status, **kwargs)
            raise document_repository.DocumentRepositoryError(
                "Document status changed concurrently; retry the transition"
            )
        return real_update(document_id, status, **kwargs)

    monkeypatch.setattr(
        document_repository,
        "update_document_status",
        competing_update,
    )

    with pytest.raises(AttachmentAlreadyProcessing):
        service.claim_retry(document.id, "alice", session.id)

    assert storage.deleted_paths == []
    current = get_document(document.id)
    assert current is not None
    assert current.status is DocumentStatus.PARSING


def test_recovery_does_not_downgrade_ready_record_from_stale_list(
    monkeypatch,
    tmp_path,
):
    _use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    document = _create_attachment(session.id, "stale-list.pdf")
    stale_record = update_document_status(
        document.id,
        DocumentStatus.PARSING,
        parser_name="pymupdf",
        parser_version="1.0",
    )
    update_document_status(
        document.id,
        DocumentStatus.INDEXING,
        parsed_path="parsed/stale-list.json",
        page_count=1,
    )
    update_document_status(document.id, DocumentStatus.READY)
    processed: list[str] = []

    monkeypatch.setattr(
        document_repository,
        "list_recoverable_processing_attachments",
        lambda **_kwargs: [stale_record],
    )

    recovery = AttachmentRecoveryService(
        _settings(tmp_path),
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
        processing_callback=processed.append,
    )
    result = recovery.recover_once()

    current = get_document(document.id)
    assert current is not None
    assert current.status is DocumentStatus.READY
    assert processed == []
    assert result.processing_recovered == 0
    assert result.failures == 1


def test_recovery_stop_signal_prevents_starting_more_records(
    monkeypatch,
    tmp_path,
):
    _use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    first = _create_attachment(session.id, "first.pdf")
    _create_attachment(session.id, "second.pdf")
    stop = False
    processed: list[str] = []

    def process(document_id):
        nonlocal stop
        processed.append(document_id)
        stop = True

    recovery = AttachmentRecoveryService(
        _settings(tmp_path, recovery_batch_size=2),
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
        processing_callback=process,
    )
    result = recovery.recover_once(stop_requested=lambda: stop)

    assert processed == [first.id]
    assert result.scanned == 1
    assert result.processing_recovered == 1
