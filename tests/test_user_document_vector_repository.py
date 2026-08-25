"""专项测试：独立 user_documents Chroma 集合。"""

from uuid import uuid4

import chromadb
import pytest

from app.repositories.knowledge_repository import KnowledgeEntry
from app.repositories.user_document_vector_repository import (
    UserDocumentVectorRepository,
)
from app.services.knowledge_chunker import KnowledgeChunk


def make_repository() -> UserDocumentVectorRepository:
    return UserDocumentVectorRepository(
        client=chromadb.EphemeralClient(),
        collection_name=f"user-documents-{uuid4().hex}",
    )


def make_chunks(count: int, source: str = "notes.md") -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            content=f"chunk {index}",
            source=source,
            title_path="Guide > Section",
            chunk_index=index,
        )
        for index in range(count)
    ]


def upsert(repository, document_id, user_id="alice", count=3, source="notes.md"):
    chunks = make_chunks(count, source)
    return repository.upsert_document_chunks(
        document_id=document_id,
        user_id=user_id,
        original_filename=source,
        version_no=1,
        chunks=chunks,
        page_ranges=[(index + 1, index + 1) for index in range(count)],
        embeddings=[[1.0, 0.0] for _ in chunks],
    )


def test_upsert_then_search_returns_hit():
    repository = make_repository()
    upsert(repository, "doc-a")

    hits = repository.search([1.0, 0.0], "alice", 3)

    assert len(hits) == 3
    assert hits[0].document_id == "doc-a"
    assert hits[0].source == "notes.md"


def test_search_filters_by_user_id():
    repository = make_repository()
    upsert(repository, "doc-a", user_id="alice")
    upsert(repository, "doc-b", user_id="bob")

    assert {hit.document_id for hit in repository.search([1.0, 0.0], "alice", 10)} == {"doc-a"}


def test_deterministic_chunk_ids_are_idempotent():
    repository = make_repository()
    upsert(repository, "doc-a", count=3)
    upsert(repository, "doc-a", count=3)

    assert repository.count() == 3
    assert repository.count_document("doc-a") == 3


def test_retry_with_fewer_chunks_removes_stale_tail():
    repository = make_repository()
    upsert(repository, "doc-a", count=5)
    upsert(repository, "doc-a", count=3)

    assert repository.count_document("doc-a") == 3


def test_same_filename_different_document_ids_do_not_collide():
    repository = make_repository()
    upsert(repository, "doc-a", count=3, source="same.md")
    upsert(repository, "doc-b", count=3, source="same.md")

    assert repository.count() == 6
    repository.delete_document("doc-a")
    assert repository.count_document("doc-a") == 0
    assert repository.count_document("doc-b") == 3


def test_delete_document_clears_all_chunks():
    repository = make_repository()
    upsert(repository, "doc-a")

    repository.delete_document("doc-a")

    assert repository.count_document("doc-a") == 0


def test_page_range_none_is_tolerated():
    repository = make_repository()
    chunks = make_chunks(1)
    repository.upsert_document_chunks(
        document_id="doc-a",
        user_id="alice",
        original_filename="notes.md",
        version_no=1,
        chunks=chunks,
        page_ranges=[(None, None)],
        embeddings=[[1.0, 0.0]],
    )

    hit = repository.search([1.0, 0.0], "alice", 1)[0]
    assert hit.page_start is None
    assert hit.page_end is None


def test_list_entries_returns_knowledge_entry_type():
    repository = make_repository()
    upsert(repository, "doc-a", count=1)

    entries = repository.list_entries()

    assert isinstance(entries[0], KnowledgeEntry)


def test_length_mismatch_raises_value_error():
    repository = make_repository()
    chunks = make_chunks(1)

    with pytest.raises(ValueError):
        repository.upsert_document_chunks(
            document_id="doc-a",
            user_id="alice",
            original_filename="notes.md",
            version_no=1,
            chunks=chunks,
            page_ranges=[],
            embeddings=[[1.0, 0.0]],
        )
