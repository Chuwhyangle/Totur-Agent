"""专项测试：知识文档摄入编排。"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.models import KnowledgeDocumentStatus
import app.repositories.knowledge_document_repository as repository
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)
from app.services.knowledge_docs.ingestion_service import (
    DUPLICATE_CONTENT,
    EMBEDDING_FAILED,
    INVALID_ENCODING,
    KnowledgeDocumentIngestionService,
)
from app.services.knowledge_docs.storage import KnowledgeDocumentStorage


class FakeEmbeddingClient:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.call_count = 0

    def embed_texts(self, texts):
        self.call_count += 1
        if self.error:
            raise self.error
        return [[1.0, 0.0] for _ in texts]


class FakeVectorRepository:
    def __init__(self):
        self.entries = {}

    def upsert_document_chunks(self, **kwargs):
        document_id = kwargs["document_id"]
        self.delete_document(document_id)
        for chunk, embedding, page_range in zip(
            kwargs["chunks"], kwargs["embeddings"], kwargs["page_ranges"]
        ):
            self.entries[f"{document_id}#{chunk.chunk_index}"] = (
                document_id,
                chunk,
                embedding,
                page_range,
            )
        return len(kwargs["chunks"])

    def delete_document(self, document_id):
        self.entries = {
            key: value for key, value in self.entries.items() if value[0] != document_id
        }

    def count_document(self, document_id):
        return sum(value[0] == document_id for value in self.entries.values())


@dataclass
class FakePdfParser:
    parsed: ParsedDocument
    name: str = "fake-pdf"
    version: str = "1"

    def parse(self, *args, **kwargs):
        return self.parsed


def make_service(tmp_path, *, embedding=None, vector=None, pdf_parser=None):
    return KnowledgeDocumentIngestionService(
        repository=repository,
        vector_repository=vector or FakeVectorRepository(),
        embedding_client=embedding or FakeEmbeddingClient(),
        storage=KnowledgeDocumentStorage(tmp_path),
        pdf_parser=pdf_parser,
    )


def test_markdown_happy_path_reaches_ready(tmp_path):
    service = make_service(tmp_path)

    record, duplicate = service.ingest_document(
        "alice", "notes.md", "text/markdown", BytesIO(b"# Guide\n\nFastAPI routes")
    )

    assert duplicate is False
    assert record.status is KnowledgeDocumentStatus.READY
    assert record.chunk_count == 1


def test_pdf_happy_path_reaches_ready(tmp_path):
    parsed = ParsedDocument(
        schema_version=2,
        document_id="pending",
        original_filename="manual.pdf",
        page_count=1,
        extracted_char_count=20,
        pages=(
            ParsedPage(
                page_number=1,
                width=100,
                height=100,
                blocks=(
                    ParsedTextBlock(0, "PDF body with enough text", (0, 0, 10, 10)),
                ),
            ),
        ),
    )
    service = make_service(tmp_path, pdf_parser=FakePdfParser(parsed))

    record, _ = service.ingest_document(
        "alice", "manual.pdf", "application/pdf", BytesIO(b"%PDF-fake")
    )

    assert record.status is KnowledgeDocumentStatus.READY
    assert record.page_count == 1


def test_l1_duplicate_returns_existing_without_new_record(tmp_path):
    embedding = FakeEmbeddingClient()
    service = make_service(tmp_path, embedding=embedding)
    first, _ = service.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"same"))
    embedding.call_count = 0

    duplicate, is_duplicate = service.ingest_document(
        "alice", "copy.md", "text/markdown", BytesIO(b"same")
    )

    assert is_duplicate is True
    assert duplicate.id == first.id
    assert embedding.call_count == 0
    assert len(repository.list_documents("alice")) == 1


def test_l2_duplicate_content_skips_embedding(tmp_path):
    embedding = FakeEmbeddingClient()
    service = make_service(tmp_path, embedding=embedding)
    service.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"same content"))
    embedding.call_count = 0

    duplicate, is_duplicate = service.ingest_document(
        "alice", "b.md", "text/markdown", BytesIO(b"same   content")
    )

    assert is_duplicate is False
    assert duplicate.status is KnowledgeDocumentStatus.FAILED
    assert duplicate.error_code == DUPLICATE_CONTENT
    assert embedding.call_count == 0


def test_same_filename_creates_version_two_and_removes_old_vectors(tmp_path):
    vector = FakeVectorRepository()
    service = make_service(tmp_path, vector=vector)
    first, _ = service.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"one"))
    second, _ = service.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"two"))

    old = repository.get_document(first.id)
    assert second.version_no == 2
    assert old is not None
    assert old.status is KnowledgeDocumentStatus.DELETED
    assert old.dedupe_key is None
    assert vector.count_document(first.id) == 0


def test_embedding_failure_leaves_no_vector_residue(tmp_path):
    vector = FakeVectorRepository()
    service = make_service(
        tmp_path,
        embedding=FakeEmbeddingClient(error=RuntimeError("offline")),
        vector=vector,
    )

    record, _ = service.ingest_document(
        "alice", "a.md", "text/markdown", BytesIO(b"body")
    )

    assert record.status is KnowledgeDocumentStatus.FAILED
    assert record.error_code == EMBEDDING_FAILED
    assert vector.count_document(record.id) == 0


def test_ready_update_failure_triggers_compensation(tmp_path, monkeypatch):
    vector = FakeVectorRepository()
    service = make_service(tmp_path, vector=vector)
    original_update = repository.update_status

    def fail_ready(document_id, status, **kwargs):
        if status is KnowledgeDocumentStatus.READY:
            return None
        return original_update(document_id, status, **kwargs)

    monkeypatch.setattr(repository, "update_status", fail_ready)
    record, _ = service.ingest_document(
        "alice", "a.md", "text/markdown", BytesIO(b"body")
    )

    assert record.status is KnowledgeDocumentStatus.FAILED
    assert vector.count_document(record.id) == 0


def test_sentinel_only_chunks_are_dropped_and_indices_are_contiguous(tmp_path):
    vector = FakeVectorRepository()
    service = make_service(tmp_path, vector=vector)
    record, _ = service.ingest_document(
        "alice",
        "a.md",
        "text/markdown",
        BytesIO(b"<!--page:1-->\n\n<!--page:2-->\n\n# Actual\n\ntext"),
    )

    indices = sorted(
        value[1].chunk_index
        for value in vector.entries.values()
        if value[0] == record.id
    )
    assert indices == list(range(len(indices)))


def test_invalid_utf8_markdown_fails_with_invalid_encoding(tmp_path):
    service = make_service(tmp_path)

    record, _ = service.ingest_document(
        "alice", "a.md", "text/markdown", BytesIO(b"\xff\xfe")
    )

    assert record.status is KnowledgeDocumentStatus.FAILED
    assert record.error_code == INVALID_ENCODING
