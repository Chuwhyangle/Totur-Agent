"""Acceptance tests for the temporary PDF attachment RAG lifecycle.

These tests intentionally exercise the public HTTP boundary and the real local
parse/chunk/index stack. External embedding/LLM calls are replaced with fakes,
and Chroma uses an in-memory EphemeralClient.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import importlib
import json
import logging
import time
from types import SimpleNamespace
from uuid import uuid4

import chromadb
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api.routes import attachments as attachments_route
from app.api.routes import chat as chat_route
from app.db import database
from app.db.models import DOCUMENTS_TABLE, DocumentStatus
from app.main import app
import app.main as main_module
from app.repositories.attachment_vector_repository import AttachmentVectorRepository
from app.repositories.document_repository import get_document, update_document_status
from app.repositories.session_repository import create_session
from app.schemas.chat import ToolTrace
from app.services.documents import attachment_processing_service as processing_module
from app.services.documents.attachment_chunker import AttachmentChunker
from app.services.documents.attachment_indexing_service import AttachmentIndexingService
from app.services.documents.attachment_processing_service import AttachmentProcessingService
from app.services.documents.attachment_retrieval_service import AttachmentRetrievalService
from app.services.documents.attachment_recovery_service import AttachmentRecoveryService
from app.services.documents.attachment_retry_service import AttachmentRetryService
from app.services.documents.parsed_document_storage import ParsedDocumentStorage
from app.services.documents.pdf_parser import PdfParser
from app.services.documents.pdf_parsing_service import PdfParsingService
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_document_service import TemporaryDocumentService
from app.services.documents.temporary_file_storage import TemporaryFileStorage


PDF_SECRET = "ORION-E2E-SECRET-7319"
SENSITIVE_CONFIG = "OPENAI_API_KEY=do-not-log-this"
SENSITIVE_PATH = r"C:\private\attachments\orion.pdf"


class FakeEmbeddingClient:
    """Deterministic three-dimensional embeddings with no network access."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            normalized = text.casefold()
            if "unrelated-weather-question" in normalized:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([1.0, 0.0, 0.0])
        return vectors


class FakeLlm:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def run(self, messages, **_kwargs):
        self.calls.append(list(messages))
        return (
            json.dumps(
                {
                    "answer": "The attachment contains the Orion code [attachment_1].",
                    "next_task": "Verify the cited page.",
                    "exercise": "Explain the Orion code.",
                    "checkpoints": ["source", "page", "answer"],
                    "source_ids": ["attachment_1"],
                }
            ),
            ToolTrace(used=False, ledger={}),
        )


@dataclass
class RagHarness:
    settings: TemporaryDocumentSettings
    vectors: AttachmentVectorRepository
    processing: AttachmentProcessingService
    documents: TemporaryDocumentService
    fake_llm: FakeLlm


@pytest.fixture
def rag_harness(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "attachment-rag-e2e.db")
    settings = TemporaryDocumentSettings(
        root_path=tmp_path / "attachment-files",
        max_bytes=2 * 1024 * 1024,
        ttl_hours=24,
        max_files_per_session=50,
        write_chunk_bytes=1024,
        max_pages=20,
        min_extracted_chars=1,
        max_extracted_chars=100_000,
        max_blocks_per_page=1000,
        chunk_chars=100,
        chunk_overlap_chars=10,
        retrieval_top_k=6,
        context_max_chars=8000,
        similarity_threshold=0.80,
    )
    vectors = AttachmentVectorRepository(
        client=chromadb.EphemeralClient(),
        collection_name=f"attachment_e2e_{uuid4().hex}",
    )
    storage = TemporaryFileStorage(settings.root_path, settings.write_chunk_bytes)
    parsed_storage = ParsedDocumentStorage(storage)
    parsing = PdfParsingService(
        settings,
        parser=PdfParser(),
        file_storage=storage,
        parsed_storage=parsed_storage,
    )
    processing = AttachmentProcessingService(
        parsing,
        AttachmentIndexingService(
            settings,
            parsed_storage,
            vectors,
            chunker=AttachmentChunker(
                settings.chunk_chars,
                settings.chunk_overlap_chars,
            ),
            embedding_client=FakeEmbeddingClient(),
        ),
    )
    documents = TemporaryDocumentService(settings, vector_repository=vectors)
    fake_llm = FakeLlm()

    retry_service = AttachmentRetryService(
        settings,
        parsed_storage=parsed_storage,
    )
    app.dependency_overrides[attachments_route.get_temporary_document_service] = (
        lambda: documents
    )
    app.dependency_overrides[attachments_route.get_attachment_retry_service] = (
        lambda: retry_service
    )
    monkeypatch.setattr(
        processing_module,
        "get_attachment_processing_service",
        lambda: processing,
    )

    retrieval = AttachmentRetrievalService(
        embedding_client=FakeEmbeddingClient(),
        vector_repository=vectors,
        settings=settings,
    )
    tutor = chat_route.tutor_agent_service
    monkeypatch.setattr(tutor, "seed_context_enabled", False)
    monkeypatch.setattr(tutor, "attachment_retrieval_service", retrieval)
    monkeypatch.setattr(tutor.react_orchestrator, "run", fake_llm.run)

    try:
        yield RagHarness(settings, vectors, processing, documents, fake_llm)
    finally:
        app.dependency_overrides.pop(
            attachments_route.get_temporary_document_service,
            None,
        )
        app.dependency_overrides.pop(
            attachments_route.get_attachment_retry_service,
            None,
        )



def _pdf_bytes(text: str = PDF_SECRET) -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def _upload_value(text: str = PDF_SECRET, filename: str = "orion-notes.pdf"):
    return SimpleNamespace(
        file=BytesIO(_pdf_bytes(text)),
        filename=filename,
        content_type="application/pdf",
    )


def _create_record(harness: RagHarness, user_id: str, session_id: int, *, name: str):
    return harness.documents.create_attachment(
        user_id,
        session_id,
        _upload_value(filename=name),
    )


def _set_status(harness: RagHarness, record_id: str, status: DocumentStatus):
    if status is DocumentStatus.UPLOADED:
        return get_document(record_id)
    if status is DocumentStatus.PARSING:
        return update_document_status(
            record_id,
            DocumentStatus.PARSING,
            parser_name="pymupdf",
            parser_version="test",
        )
    if status is DocumentStatus.INDEXING:
        parsing = harness.processing.parsing_service
        return parsing.parse_attachment(record_id)
    if status is DocumentStatus.FAILED:
        update_document_status(
            record_id,
            DocumentStatus.PARSING,
            parser_name="pymupdf",
            parser_version="test",
        )
        return update_document_status(
            record_id,
            DocumentStatus.FAILED,
            error_code="EMBEDDING_FAILED",
            error_message="retryable test failure",
        )
    if status is DocumentStatus.READY:
        return harness.processing.process_attachment(record_id)
    raise ValueError(status)



@contextmanager
def _client(
    raise_server_exceptions: bool = False,
    *,
    run_lifespan: bool = False,
):
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    try:
        if run_lifespan:
            with client:
                yield client
        else:
            # Ordinary API tests must not let startup recovery race the state
            # that the request itself is intended to exercise.
            yield client
    finally:
        client.close()


def _create_session_http(client: TestClient, user_id: str = "alice") -> int:
    response = client.post(
        "/sessions",
        json={"user_id": user_id, "title": "Attachment RAG acceptance"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _chat(client: TestClient, user_id: str, session_id: int, document_id: str, message: str):
    return client.post(
        "/chat",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "attachment_ids": [document_id],
        },
    )


def _backdate(record_id: str, *, expired: bool = False) -> None:
    connection = database.get_connection()
    try:
        values: list[str] = [
            (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        ]
        assignments = "updated_at = ?"
        if expired:
            assignments += ", expires_at = ?"
            values.append(
                (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            )
        values.append(record_id)
        connection.execute(
            f"UPDATE {DOCUMENTS_TABLE} SET {assignments} WHERE id = ?",
            values,
        )
        connection.commit()
    finally:
        connection.close()


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_upload_persists_before_lazy_processing_factory_failure(
    monkeypatch,
    tmp_path,
    caplog,
):
    """Embedding/Chroma construction failure must not break upload durability."""

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "lazy-upload.db")
    settings = TemporaryDocumentSettings(
        root_path=tmp_path / "lazy-files",
        max_bytes=2 * 1024 * 1024,
        max_files_per_session=5,
        write_chunk_bytes=1024,
        min_extracted_chars=1,
    )
    documents = TemporaryDocumentService(
        settings,
        vector_repository=AttachmentVectorRepository(
            chromadb.EphemeralClient(),
            f"lazy_{uuid4().hex}",
        ),
    )

    def failing_factory():
        raise RuntimeError(
            f"embedding unavailable {SENSITIVE_CONFIG} {SENSITIVE_PATH} {PDF_SECRET}"
        )

    app.dependency_overrides[attachments_route.get_temporary_document_service] = (
        lambda: documents
    )
    eager_factory = getattr(
        attachments_route,
        "get_attachment_processing_service",
        None,
    )
    if eager_factory is not None:
        app.dependency_overrides[eager_factory] = failing_factory
    monkeypatch.setattr(
        processing_module,
        "get_attachment_processing_service",
        failing_factory,
    )
    caplog.set_level(logging.ERROR)

    try:
        with _client() as client:
            session_id = _create_session_http(client)
            response = client.post(
                f"/sessions/{session_id}/attachments",
                data={"user_id": "alice"},
                files={
                    "file": (
                        "orion.pdf",
                        _pdf_bytes(),
                        "application/pdf",
                    )
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    document_id = response.json()["id"]
    record = get_document(document_id)
    assert record is not None
    assert documents.storage.resolve(record.storage_path).read_bytes().startswith(b"%PDF")
    assert record.status in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}
    if record.status is DocumentStatus.FAILED:
        assert record.error_code == "PROCESSING_SERVICE_UNAVAILABLE"

    logs = caplog.text
    assert document_id in logs
    assert "RuntimeError" in logs
    assert "status=" in logs
    assert PDF_SECRET not in logs
    assert SENSITIVE_CONFIG not in logs
    assert SENSITIVE_PATH not in logs
    assert str(settings.root_path) not in logs


@pytest.mark.parametrize(
    ("initial_status", "expected_status", "expected_error"),
    [
        (DocumentStatus.UPLOADED, 202, None),
        (DocumentStatus.FAILED, 202, None),
        (DocumentStatus.PARSING, 409, "attachment_already_processing"),
        (DocumentStatus.INDEXING, 409, "attachment_already_processing"),
        (DocumentStatus.READY, 409, "attachment_retry_not_allowed"),
    ],
)
def test_retry_http_status_matrix(
    rag_harness,
    initial_status,
    expected_status,
    expected_error,
):
    session = create_session("alice")
    record = _create_record(
        rag_harness,
        "alice",
        session.id,
        name=f"{initial_status.value.lower()}.pdf",
    )
    _set_status(rag_harness, record.id, initial_status)

    with _client() as client:
        response = client.post(
            f"/sessions/{session.id}/attachments/{record.id}/retry",
            params={"user_id": "alice"},
        )

    assert response.status_code == expected_status
    if expected_error is not None:
        assert response.json() == {"detail": {"error": expected_error}}
    else:
        assert _wait_until(
            lambda: (
                get_document(record.id) is not None
                and get_document(record.id).status is DocumentStatus.READY
            )
        )
        assert rag_harness.vectors.count_document(record.id) > 0


@pytest.mark.parametrize("access_case", ["other_user", "cross_session", "missing", "expired"])
def test_retry_hides_ownership_session_ttl_and_existence(rag_harness, access_case):
    session = create_session("alice")
    other_session = create_session("alice")
    record = _create_record(rag_harness, "alice", session.id, name="owned.pdf")
    request_session = session.id
    request_user = "alice"
    document_id = record.id

    if access_case == "other_user":
        request_user = "mallory"
    elif access_case == "cross_session":
        request_session = other_session.id
    elif access_case == "missing":
        document_id = "00000000-0000-0000-0000-000000000000"
    elif access_case == "expired":
        _backdate(record.id, expired=True)

    with _client() as client:
        response = client.post(
            f"/sessions/{request_session}/attachments/{document_id}/retry",
            params={"user_id": request_user},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "attachment_not_found"}}
    if access_case != "expired":
        assert get_document(record.id) is not None


def test_ready_attachment_with_missing_vectors_returns_stable_409_without_llm(
    rag_harness,
):
    session = create_session("alice")
    record = _create_record(rag_harness, "alice", session.id, name="indexed.pdf")
    ready = rag_harness.processing.process_attachment(record.id)
    assert ready.status is DocumentStatus.READY
    assert rag_harness.vectors.count_document(record.id) > 0
    rag_harness.vectors.delete_document(record.id)

    with _client() as client:
        response = _chat(
            client,
            "alice",
            session.id,
            record.id,
            "What is the Orion code?",
        )

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "attachment_index_missing"}}
    assert rag_harness.fake_llm.calls == []


def test_low_similarity_is_distinct_empty_recall_and_never_calls_llm(rag_harness):
    session = create_session("alice")
    record = _create_record(rag_harness, "alice", session.id, name="similarity.pdf")
    ready = rag_harness.processing.process_attachment(record.id)
    assert ready.status is DocumentStatus.READY
    assert rag_harness.vectors.count_document(record.id) > 0

    with _client() as client:
        response = _chat(
            client,
            "alice",
            session.id,
            record.id,
            "unrelated-weather-question",
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"error": "attachment_no_relevant_evidence"}
    }
    assert rag_harness.fake_llm.calls == []


def test_startup_recovery_state_matrix_is_bounded_and_failure_isolated(
    monkeypatch,
    rag_harness,
):
    """Startup recovers work, cleans terminal rows, and never blocks health."""

    session = create_session("alice")
    uploaded = _create_record(rag_harness, "alice", session.id, name="uploaded.pdf")

    parsing = _create_record(rag_harness, "alice", session.id, name="parsing.pdf")
    update_document_status(
        parsing.id,
        DocumentStatus.PARSING,
        parser_name="pymupdf",
        parser_version="test",
    )
    _backdate(parsing.id)

    indexing = _create_record(rag_harness, "alice", session.id, name="indexing.pdf")
    rag_harness.processing.parsing_service.parse_attachment(indexing.id)
    _backdate(indexing.id)

    ready = _create_record(rag_harness, "alice", session.id, name="ready.pdf")
    rag_harness.processing.process_attachment(ready.id)
    ready_vector_count = rag_harness.vectors.count_document(ready.id)

    expired = _create_record(rag_harness, "alice", session.id, name="expired.pdf")
    _backdate(expired.id, expired=True)

    deleting = _create_record(rag_harness, "alice", session.id, name="deleting.pdf")
    update_document_status(deleting.id, DocumentStatus.DELETING)
    _backdate(deleting.id)

    deleted = _create_record(rag_harness, "alice", session.id, name="deleted.pdf")
    update_document_status(deleted.id, DocumentStatus.DELETING)
    update_document_status(deleted.id, DocumentStatus.DELETED)
    _backdate(deleted.id)

    failing = _create_record(rag_harness, "alice", session.id, name="failing.pdf")

    class SelectiveProcessingService:
        def process_attachment(self, document_id):
            if document_id == failing.id:
                raise RuntimeError("isolated recovery failure")
            return rag_harness.processing.process_attachment(document_id)

    selective = SelectiveProcessingService()
    recovery = AttachmentRecoveryService(
        rag_harness.settings,
        processing_callback=selective.process_attachment,
        cleanup_service_factory=lambda: rag_harness.documents,
    )
    monkeypatch.setattr(
        main_module,
        "get_attachment_recovery_service",
        lambda: recovery,
    )

    with _client(run_lifespan=True) as client:
        health = client.get("/health")
        assert health.status_code == 200
        recovered = _wait_until(
            lambda: all(
                get_document(document_id) is not None
                and get_document(document_id).status is DocumentStatus.READY
                for document_id in (uploaded.id, parsing.id, indexing.id)
            )
            and get_document(deleting.id) is None
            and get_document(deleted.id) is None,
            timeout=5.0,
        )

    assert recovered
    assert get_document(failing.id) is not None
    assert get_document(failing.id).status in {
        DocumentStatus.UPLOADED,
        DocumentStatus.FAILED,
    }
    assert get_document(expired.id) is None or get_document(expired.id).status is not DocumentStatus.READY
    assert rag_harness.vectors.count_document(expired.id) == 0
    assert get_document(ready.id).status is DocumentStatus.READY
    assert rag_harness.vectors.count_document(ready.id) == ready_vector_count


