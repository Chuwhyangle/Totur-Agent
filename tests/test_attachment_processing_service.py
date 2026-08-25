"""Tests for the parse-and-index attachment application pipeline."""

import pytest

from app.db import database
from app.db.models import DocumentStatus
from app.repositories.document_repository import create_attachment_document, get_document, update_document_status
from app.repositories.session_repository import create_session
from app.services.documents.attachment_processing_service import (
    AttachmentAlreadyProcessing,
    AttachmentProcessingNotAllowed,
    AttachmentProcessingService,
    process_attachment_background,
)


class SuccessfulParsingService:
    def __init__(self):
        self.calls = []

    def parse_attachment(self, document_id):
        self.calls.append(document_id)
        update_document_status(
            document_id,
            DocumentStatus.PARSING,
            parser_name="fake-parser",
            parser_version="1.0",
        )
        return update_document_status(
            document_id,
            DocumentStatus.INDEXING,
            parsed_path=f"parsed/{document_id}.json",
            page_count=1,
        )


class SuccessfulIndexingService:
    def __init__(self):
        self.calls = []

    def index_attachment(self, document_id):
        self.calls.append(document_id)
        return update_document_status(document_id, DocumentStatus.READY)


class FailedParsingService:
    def parse_attachment(self, document_id):
        update_document_status(document_id, DocumentStatus.PARSING)
        return update_document_status(
            document_id,
            DocumentStatus.FAILED,
            error_code="INVALID_PDF",
        )


class ExplodingProcessingService:
    def process_attachment(self, _document_id):
        raise RuntimeError("background failed")


def create_record(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session = create_session("alice")
    return create_attachment_document(
        user_id="alice",
        session_id=session.id,
        original_filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        storage_path="paper.pdf",
        expires_at="2030-01-01T00:00:00+00:00",
    )


def test_processing_runs_parsing_then_indexing_to_ready(monkeypatch, tmp_path):
    record = create_record(monkeypatch, tmp_path)
    parsing = SuccessfulParsingService()
    indexing = SuccessfulIndexingService()
    service = AttachmentProcessingService(parsing, indexing)

    ready = service.process_attachment(record.id)

    assert ready.status is DocumentStatus.READY
    assert parsing.calls == [record.id]
    assert indexing.calls == [record.id]


def test_processing_marks_parsed_attachment_ready_without_indexer(monkeypatch, tmp_path):
    record = create_record(monkeypatch, tmp_path)
    parsing = SuccessfulParsingService()

    ready = AttachmentProcessingService(parsing).process_attachment(record.id)

    assert ready.status is DocumentStatus.READY
    assert get_document(record.id).status is DocumentStatus.READY


def test_processing_stops_after_stable_parsing_failure(monkeypatch, tmp_path):
    record = create_record(monkeypatch, tmp_path)
    indexing = SuccessfulIndexingService()
    service = AttachmentProcessingService(FailedParsingService(), indexing)

    failed = service.process_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "INVALID_PDF"
    assert indexing.calls == []


def test_processing_is_idempotent_for_ready_attachment(monkeypatch, tmp_path):
    record = create_record(monkeypatch, tmp_path)
    parsing = SuccessfulParsingService()
    indexing = SuccessfulIndexingService()
    service = AttachmentProcessingService(parsing, indexing)
    ready = service.process_attachment(record.id)

    assert service.process_attachment(record.id) == ready
    assert parsing.calls == [record.id]
    assert indexing.calls == [record.id]


@pytest.mark.parametrize("status", [DocumentStatus.PARSING, DocumentStatus.INDEXING])
def test_processing_rejects_an_attachment_already_claimed(monkeypatch, tmp_path, status):
    record = create_record(monkeypatch, tmp_path)
    update_document_status(record.id, DocumentStatus.PARSING)
    if status is DocumentStatus.INDEXING:
        update_document_status(
            record.id,
            DocumentStatus.INDEXING,
            parsed_path="parsed/result.json",
            page_count=1,
            parser_name="fake-parser",
            parser_version="1.0",
        )
    service = AttachmentProcessingService(SuccessfulParsingService(), SuccessfulIndexingService())

    with pytest.raises(AttachmentAlreadyProcessing):
        service.process_attachment(record.id)


def test_processing_rejects_deleting_attachment(monkeypatch, tmp_path):
    record = create_record(monkeypatch, tmp_path)
    update_document_status(record.id, DocumentStatus.DELETING)
    service = AttachmentProcessingService(SuccessfulParsingService(), SuccessfulIndexingService())

    with pytest.raises(AttachmentProcessingNotAllowed):
        service.process_attachment(record.id)


def test_background_wrapper_logs_and_does_not_escape_after_response(caplog):
    process_attachment_background("doc-1", ExplodingProcessingService())

    assert "attachment_background_processing_failed" in caplog.text
    assert "RuntimeError" in caplog.text
