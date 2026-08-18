"""Tests for parsed attachment embedding and Chroma publication."""

from datetime import datetime, timezone
from uuid import uuid4

import chromadb

from app.db import database
from app.db.models import DocumentStatus
import app.repositories.document_repository as document_repository
from app.repositories.attachment_vector_repository import AttachmentVectorRepository
from app.repositories.document_repository import create_attachment_document, update_document_status
from app.repositories.session_repository import create_session
from app.services.documents.attachment_chunker import AttachmentChunker
from app.services.documents.attachment_indexing_service import AttachmentIndexingService
from app.services.documents.parsed_document import ParsedDocument, ParsedPage, ParsedTextBlock
from app.services.documents.parsed_document_storage import ParsedDocumentStorage
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


class FakeEmbeddingClient:
    def __init__(self, *, fail=False, mismatch=False):
        self.fail = fail
        self.mismatch = mismatch
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("embedding unavailable")
        if self.mismatch:
            return []
        return [[float(index + 1), 1.0] for index, _text in enumerate(texts)]


class FailingVectorRepository:
    def __init__(self, delegate):
        self.delegate = delegate

    def upsert_document_chunks(self, **kwargs):
        self.delegate.upsert_document_chunks(**kwargs)
        raise RuntimeError("chroma unavailable")

    def delete_document(self, document_id):
        self.delegate.delete_document(document_id)


def make_context(monkeypatch, tmp_path, *, parsed_document=None, expires_at="2030-01-01T00:00:00+00:00", embedding_client=None, vector_repository=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session = create_session("alice")
    settings = TemporaryDocumentSettings(root_path=tmp_path / "files", min_extracted_chars=1)
    files = TemporaryFileStorage(settings.root_path, settings.write_chunk_bytes)
    source_key = "original.pdf"
    source_path = files.resolve(source_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"%PDF-1.7 original")
    record = create_attachment_document(
        user_id="alice",
        session_id=session.id,
        original_filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=source_path.stat().st_size,
        storage_path=source_key,
        expires_at=expires_at,
    )
    parsed = parsed_document or ParsedDocument(
        schema_version=1,
        document_id=record.id,
        original_filename=record.original_filename,
        page_count=2,
        extracted_char_count=9,
        pages=(
            ParsedPage(1, 100.0, 100.0, (ParsedTextBlock(0, "alpha", (0.0, 0.0, 1.0, 1.0)),)),
            ParsedPage(2, 100.0, 100.0, (ParsedTextBlock(0, "beta", (0.0, 0.0, 1.0, 1.0)),)),
        ),
    )
    parsed_storage = ParsedDocumentStorage(files)
    parsed_key = parsed_storage.write_json(record.id, parsed)
    update_document_status(
        record.id,
        DocumentStatus.PARSING,
        parser_name="test-parser",
        parser_version="1.0",
    )
    update_document_status(
        record.id,
        DocumentStatus.INDEXING,
        parsed_path=parsed_key,
        page_count=2,
    )
    vectors = vector_repository or AttachmentVectorRepository(
        client=chromadb.EphemeralClient(),
        collection_name=f"indexing-{uuid4().hex}",
    )
    embedder = embedding_client or FakeEmbeddingClient()
    service = AttachmentIndexingService(
        settings,
        parsed_storage,
        vectors,
        chunker=AttachmentChunker(chunk_chars=100, overlap_chars=10),
        embedding_client=embedder,
        now_provider=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    return service, record, source_path, parsed_storage, vectors, embedder


def test_indexing_publishes_ready_and_keeps_original_and_json(monkeypatch, tmp_path):
    service, record, source_path, parsed_storage, vectors, embedder = make_context(monkeypatch, tmp_path)

    ready = service.index_attachment(record.id)

    assert ready.status is DocumentStatus.READY
    assert ready.parsed_path == f"parsed/{record.id}.json"
    assert ready.error_code is None
    assert source_path.exists()
    assert parsed_storage.exists(ready.parsed_path)
    assert vectors.count_document(record.id) == 2
    assert embedder.calls == [["alpha", "beta"]]


def test_embedding_failure_marks_failed_without_vectors(monkeypatch, tmp_path):
    embedder = FakeEmbeddingClient(fail=True)
    service, record, source_path, _storage, vectors, _ = make_context(
        monkeypatch, tmp_path, embedding_client=embedder
    )

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "EMBEDDING_FAILED"
    assert vectors.count_document(record.id) == 0
    assert source_path.exists()


def test_embedding_count_mismatch_is_stable_failure(monkeypatch, tmp_path):
    service, record, _source, _storage, vectors, _ = make_context(
        monkeypatch, tmp_path, embedding_client=FakeEmbeddingClient(mismatch=True)
    )

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "EMBEDDING_FAILED"
    assert vectors.count_document(record.id) == 0


def test_partial_vector_write_is_compensated_and_marked_failed(monkeypatch, tmp_path):
    delegate = AttachmentVectorRepository(
        client=chromadb.EphemeralClient(),
        collection_name=f"failing-{uuid4().hex}",
    )
    service, record, source_path, _storage, _vectors, _ = make_context(
        monkeypatch,
        tmp_path,
        vector_repository=FailingVectorRepository(delegate),
    )

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "VECTOR_INDEX_FAILED"
    assert delegate.count_document(record.id) == 0
    assert source_path.exists()


def test_ready_metadata_failure_deletes_vectors(monkeypatch, tmp_path):
    service, record, _source, _storage, vectors, _ = make_context(monkeypatch, tmp_path)
    real_update = document_repository.update_document_status

    def fail_ready(document_id, status, **metadata):
        if DocumentStatus(status) is DocumentStatus.READY:
            raise RuntimeError("sqlite unavailable")
        return real_update(document_id, status, **metadata)

    monkeypatch.setattr(document_repository, "update_document_status", fail_ready)

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "VECTOR_INDEX_FAILED"
    assert vectors.count_document(record.id) == 0


def test_parsed_identity_mismatch_never_embeds_or_indexes(monkeypatch, tmp_path):
    invalid = ParsedDocument(
        schema_version=1,
        document_id="wrong-document",
        original_filename="paper.pdf",
        page_count=2,
        extracted_char_count=9,
        pages=(
            ParsedPage(1, 1.0, 1.0, (ParsedTextBlock(0, "alpha", (0.0, 0.0, 1.0, 1.0)),)),
            ParsedPage(2, 1.0, 1.0, (ParsedTextBlock(0, "beta", (0.0, 0.0, 1.0, 1.0)),)),
        ),
    )
    service, record, _source, _storage, vectors, embedder = make_context(
        monkeypatch, tmp_path, parsed_document=invalid
    )

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "PARSED_DOCUMENT_INVALID"
    assert embedder.calls == []
    assert vectors.count_document(record.id) == 0


def test_expired_attachment_is_failed_before_embedding(monkeypatch, tmp_path):
    service, record, source_path, _storage, vectors, embedder = make_context(
        monkeypatch,
        tmp_path,
        expires_at="2030-01-01T00:00:00+00:00",
    )
    service._now_provider = lambda: datetime(2031, 1, 1, tzinfo=timezone.utc)

    failed = service.index_attachment(record.id)

    assert failed.status is DocumentStatus.FAILED
    assert failed.error_code == "ATTACHMENT_EXPIRED_DURING_PROCESSING"
    assert embedder.calls == []
    assert vectors.count_document(record.id) == 0
    assert source_path.exists()
