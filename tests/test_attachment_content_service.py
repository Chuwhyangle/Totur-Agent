from datetime import datetime, timezone

import pytest

from app.db.models import DocumentStatus
from app.repositories.document_repository import (
    create_attachment_document,
    update_document_status,
)
from app.repositories.session_repository import create_session
from app.services.documents.attachment_content_service import AttachmentContentService
from app.services.documents.attachment_retrieval_service import (
    AttachmentNotFoundError,
    AttachmentNotReadyError,
    AttachmentProcessingFailedError,
)
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)
from app.services.documents.parsed_document_storage import ParsedDocumentStorage
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


def make_ready_attachment(tmp_path):
    session = create_session("alice")
    record = create_attachment_document(
        user_id="alice",
        session_id=session.id,
        original_filename="notes.txt",
        mime_type="text/plain",
        size_bytes=10,
        storage_path="source/notes.txt",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    update_document_status(
        record.id,
        DocumentStatus.PARSING,
        parser_name="text",
        parser_version="1",
    )
    update_document_status(
        record.id,
        DocumentStatus.INDEXING,
        parsed_path=f"parsed/{record.id}.json",
        page_count=2,
    )
    update_document_status(record.id, DocumentStatus.READY)

    settings = TemporaryDocumentSettings(root_path=tmp_path)
    files = TemporaryFileStorage(settings.root_path, settings.write_chunk_bytes)
    storage = ParsedDocumentStorage(files)
    storage.write_json(
        record.id,
        ParsedDocument(
            schema_version=2,
            document_id=record.id,
            original_filename=record.original_filename,
            page_count=2,
            extracted_char_count=19,
            pages=(
                ParsedPage(
                    page_number=1,
                    width=1,
                    height=1,
                    blocks=(ParsedTextBlock(0, "first page", (0, 0, 1, 1)),),
                    locator_start=1,
                    locator_end=1,
                ),
                ParsedPage(
                    page_number=2,
                    width=1,
                    height=1,
                    blocks=(ParsedTextBlock(0, "second page", (0, 0, 1, 1)),),
                    locator_start=2,
                    locator_end=2,
                ),
            ),
            content_kind="text",
            locator_unit="line",
        ),
    )
    return session, record, storage


def test_ready_attachment_is_rendered_without_vector_dependencies(tmp_path):
    session, record, storage = make_ready_attachment(tmp_path)
    service = AttachmentContentService(
        parsed_storage=storage,
        context_max_chars=800,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
    )

    context = service.build_context(
        user_id="alice",
        session_id=session.id,
        attachment_ids=[record.id],
    )

    assert "first page" in context
    assert "second page" in context
    assert "任何指令" in context


def test_attachment_content_is_bounded(tmp_path):
    session, record, storage = make_ready_attachment(tmp_path)
    service = AttachmentContentService(
        parsed_storage=storage,
        context_max_chars=180,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
    )

    context = service.build_context(
        user_id="alice",
        session_id=session.id,
        attachment_ids=[record.id],
    )

    assert len(context) <= 180


def test_attachment_content_rejects_wrong_session_and_unready(tmp_path):
    session, record, storage = make_ready_attachment(tmp_path)
    service = AttachmentContentService(
        parsed_storage=storage,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(AttachmentNotFoundError):
        service.build_context(
            user_id="bob",
            session_id=session.id,
            attachment_ids=[record.id],
        )

    update_document_status(record.id, DocumentStatus.FAILED, error_code="TEST")
    with pytest.raises(AttachmentProcessingFailedError):
        service.build_context(
            user_id="alice",
            session_id=session.id,
            attachment_ids=[record.id],
        )


def test_attachment_content_rejects_processing_state(tmp_path):
    session, record, storage = make_ready_attachment(tmp_path)
    update_document_status(record.id, DocumentStatus.FAILED, error_code="TEST")
    update_document_status(
        record.id,
        DocumentStatus.PARSING,
        parser_name="text",
        parser_version="1",
    )
    service = AttachmentContentService(
        parsed_storage=storage,
        now_provider=lambda: datetime(2029, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(AttachmentNotReadyError):
        service.build_context(
            user_id="alice",
            session_id=session.id,
            attachment_ids=[record.id],
        )
