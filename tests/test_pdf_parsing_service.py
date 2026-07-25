"""Tests for PDF parsing lifecycle orchestration and compensation."""

from datetime import datetime, timezone
from pathlib import Path

import pymupdf
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
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.pdf_parser import PdfContentLimitExceeded, PdfParser
from app.services.documents.pdf_parsing_service import (
    AlreadyParsingError,
    AttachmentParsingExpired,
    AttachmentParsingNotAllowed,
    PdfParsingService,
)
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "parsing.db")


def create_pdf(path: Path, text: str | None = "Extractable PDF text content"):
    document = pymupdf.open()
    try:
        page = document.new_page()
        if text is not None:
            page.insert_text((72, 72), text)
        document.save(path)
    finally:
        document.close()


def create_encrypted_pdf(path: Path):
    document = pymupdf.open()
    try:
        document.new_page().insert_text((72, 72), "protected content")
        document.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    finally:
        document.close()


def make_context(
    monkeypatch,
    tmp_path,
    *,
    kind="text",
    expires_at="2030-01-01T00:00:00+00:00",
    max_pages=10,
    min_chars=3,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    settings = TemporaryDocumentSettings(
        root_path=tmp_path / "attachment-files",
        max_bytes=4096,
        ttl_hours=24,
        max_files_per_session=5,
        write_chunk_bytes=1024,
        max_pages=max_pages,
        min_extracted_chars=min_chars,
    )
    files = TemporaryFileStorage(settings.root_path, settings.write_chunk_bytes)
    source_key = "source.pdf"
    source_path = files.resolve(source_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "text":
        create_pdf(source_path)
    elif kind == "blank":
        create_pdf(source_path, None)
    elif kind == "corrupt":
        source_path.write_bytes(b"%PDF-corrupt")
    elif kind == "encrypted":
        create_encrypted_pdf(source_path)
    else:
        raise ValueError(kind)

    record = create_attachment_document(
        user_id="alice",
        session_id=session.id,
        original_filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=source_path.stat().st_size,
        storage_path=source_key,
        expires_at=expires_at,
    )
    parsed_storage = ParsedDocumentStorage(files)
    service = PdfParsingService(
        settings,
        parser=PdfParser(),
        file_storage=files,
        parsed_storage=parsed_storage,
    )
    return service, record, source_path, parsed_storage


def test_uploaded_transitions_through_parsing_to_indexing(monkeypatch, tmp_path):
    service, record, _source, _parsed_storage = make_context(
        monkeypatch,
        tmp_path,
    )
    transitions = []
    real_update = document_repository.update_document_status

    def track_update(document_id, status, **metadata):
        transitions.append(DocumentStatus(status))
        return real_update(document_id, status, **metadata)

    monkeypatch.setattr(document_repository, "update_document_status", track_update)

    ready = service.parse_attachment(record.id)

    assert transitions == [DocumentStatus.PARSING, DocumentStatus.INDEXING]
    assert ready.status is DocumentStatus.INDEXING


def test_indexing_metadata_and_json_are_consistent(monkeypatch, tmp_path):
    service, record, _source, parsed_storage = make_context(monkeypatch, tmp_path)

    ready = service.parse_attachment(record.id)
    payload = parsed_storage.read_json(ready.parsed_path)

    assert ready.parsed_path == f"parsed/{record.id}.json"
    assert not Path(ready.parsed_path).is_absolute()
    assert ready.page_count == 1
    assert ready.parser_name == "pymupdf"
    assert ready.parser_version == pymupdf.__version__
    assert payload["document_id"] == ready.id
    assert payload["page_count"] == ready.page_count


@pytest.mark.parametrize(
    ("kind", "error_code"),
    [
        ("corrupt", "INVALID_PDF"),
        ("encrypted", "ENCRYPTED_PDF_NOT_SUPPORTED"),
        ("blank", "NO_EXTRACTABLE_TEXT"),
    ],
)
def test_known_parser_failures_become_stable_failed_records(
    monkeypatch,
    tmp_path,
    kind,
    error_code,
):
    service, record, source_path, _storage = make_context(
        monkeypatch,
        tmp_path,
        kind=kind,
        min_chars=1,
    )

    failed = service.parse_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == error_code
    assert source_path.exists()
    assert failed.parsed_path is None


def test_failed_attachment_can_retry_to_indexing(monkeypatch, tmp_path):
    service, record, source_path, _storage = make_context(
        monkeypatch,
        tmp_path,
        kind="corrupt",
    )
    failed = service.parse_attachment(record.id)
    assert failed.status is DocumentStatus.FAILED

    create_pdf(source_path, "Valid text after a retry")
    ready = service.parse_attachment(record.id)

    assert ready.status is DocumentStatus.INDEXING
    assert ready.error_code is None
    assert ready.error_message is None
    assert ready.parsed_path is not None


def test_indexing_attachment_is_returned_without_reparsing(monkeypatch, tmp_path):
    service, record, _source, _storage = make_context(monkeypatch, tmp_path)
    first = service.parse_attachment(record.id)

    def fail_parse(**_kwargs):
        raise AssertionError("INDEXING attachments must not be parsed again")

    monkeypatch.setattr(service.parser, "parse", fail_parse)

    assert service.parse_attachment(record.id) == first


def test_parsing_attachment_returns_stable_already_parsing(monkeypatch, tmp_path):
    service, record, _source, _storage = make_context(monkeypatch, tmp_path)
    update_document_status(record.id, DocumentStatus.PARSING)

    with pytest.raises(AlreadyParsingError):
        service.parse_attachment(record.id)


def test_concurrent_parsing_claim_returns_stable_already_parsing(
    monkeypatch,
    tmp_path,
):
    service, record, _source, _storage = make_context(monkeypatch, tmp_path)
    real_update = document_repository.update_document_status

    def lose_claim(document_id, status, **metadata):
        if DocumentStatus(status) is DocumentStatus.PARSING:
            real_update(document_id, status, **metadata)
            raise document_repository.DocumentRepositoryError(
                "concurrent claim"
            )
        return real_update(document_id, status, **metadata)

    monkeypatch.setattr(document_repository, "update_document_status", lose_claim)

    with pytest.raises(AlreadyParsingError):
        service.parse_attachment(record.id)


@pytest.mark.parametrize("terminal_status", [DocumentStatus.DELETING, DocumentStatus.DELETED])
def test_deleting_and_deleted_attachments_are_not_parsed(
    monkeypatch,
    tmp_path,
    terminal_status,
):
    service, record, _source, _storage = make_context(monkeypatch, tmp_path)
    update_document_status(record.id, DocumentStatus.DELETING)
    if terminal_status is DocumentStatus.DELETED:
        update_document_status(record.id, DocumentStatus.DELETED)

    with pytest.raises(AttachmentParsingNotAllowed):
        service.parse_attachment(record.id)


def test_expired_attachment_is_not_parsed(monkeypatch, tmp_path):
    service, record, _source, _storage = make_context(monkeypatch, tmp_path)
    service._now_provider = lambda: datetime(2031, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(AttachmentParsingExpired):
        service.parse_attachment(record.id)

    assert get_document(record.id).status is DocumentStatus.UPLOADED


def test_json_write_failure_marks_failed_without_artifacts(monkeypatch, tmp_path):
    service, record, source_path, parsed_storage = make_context(
        monkeypatch,
        tmp_path,
    )

    def fail_write(_document_id, _payload):
        raise ParsedDocumentStorageError("disk failed")

    monkeypatch.setattr(parsed_storage, "write_json", fail_write)

    failed = service.parse_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "PDF_PARSE_FAILED"
    assert source_path.exists()
    assert list(service.settings.root_path.rglob("*.json")) == []
    assert list(service.settings.root_path.rglob("*.part")) == []


def test_indexing_update_failure_deletes_json_and_marks_failed(monkeypatch, tmp_path):
    service, record, source_path, _storage = make_context(monkeypatch, tmp_path)
    real_update = document_repository.update_document_status

    def fail_ready(document_id, status, **metadata):
        if DocumentStatus(status) is DocumentStatus.INDEXING:
            raise RuntimeError("database unavailable")
        return real_update(document_id, status, **metadata)

    monkeypatch.setattr(document_repository, "update_document_status", fail_ready)

    failed = service.parse_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "PDF_PARSE_FAILED"
    assert failed.parsed_path is None
    assert source_path.exists()
    assert list(service.settings.root_path.rglob("*.json")) == []


def test_parser_failure_never_deletes_original_pdf(monkeypatch, tmp_path):
    service, record, source_path, _storage = make_context(
        monkeypatch,
        tmp_path,
        kind="corrupt",
    )

    service.parse_attachment(record.id)

    assert source_path.exists()


def test_parser_identity_mismatch_marks_failed_without_json(monkeypatch, tmp_path):
    service, record, source_path, _storage = make_context(monkeypatch, tmp_path)

    class WrongIdentityParser:
        name = "wrong-parser"
        version = "1.0"

        def parse(self, **_kwargs):
            return ParsedDocument(
                schema_version=1,
                document_id="wrong-id",
                original_filename=record.original_filename,
                page_count=1,
                extracted_char_count=4,
                pages=(
                    ParsedPage(
                        1,
                        10.0,
                        10.0,
                        (ParsedTextBlock(0, "text", (0.0, 0.0, 1.0, 1.0)),),
                    ),
                ),
            )

    service.parser = WrongIdentityParser()

    failed = service.parse_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "PARSED_DOCUMENT_INVALID"
    assert source_path.exists()
    assert list(service.settings.root_path.rglob("*.json")) == []


def test_content_limit_failure_writes_no_parsed_json(monkeypatch, tmp_path):
    service, record, source_path, _storage = make_context(monkeypatch, tmp_path)

    def fail_limit(**_kwargs):
        raise PdfContentLimitExceeded("too much extracted text")

    monkeypatch.setattr(service.parser, "parse", fail_limit)

    failed = service.parse_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "PDF_CONTENT_LIMIT_EXCEEDED"
    assert source_path.exists()
    assert list(service.settings.root_path.rglob("*.json")) == []
