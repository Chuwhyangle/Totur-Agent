"""Tests for isolated temporary attachment vector storage."""

from uuid import uuid4

import chromadb
import pytest

from app.repositories.attachment_vector_repository import AttachmentVectorRepository
from app.services.documents.attachment_chunker import AttachmentChunk


def make_repository():
    return AttachmentVectorRepository(
        client=chromadb.EphemeralClient(),
        collection_name=f"temporary-attachments-{uuid4().hex}",
    )


def chunk(document_id, index, text, page):
    return AttachmentChunk(
        chunk_id=f"{document_id}:{index}",
        document_id=document_id,
        chunk_index=index,
        text=text,
        page_start=page,
        page_end=page,
        original_filename=f"{document_id}.pdf",
    )


def test_upsert_search_and_metadata_are_session_scoped():
    repository = make_repository()
    repository.upsert_document_chunks(
        [chunk("doc-a", 0, "alpha", 1), chunk("doc-a", 1, "beta", 2)],
        [[1.0, 0.0], [0.0, 1.0]],
        user_id="alice",
        session_id=10,
        expires_at="2030-01-01T00:00:00+00:00",
    )
    repository.upsert_document_chunks(
        [chunk("doc-b", 0, "private", 3)],
        [[1.0, 0.0]],
        user_id="bob",
        session_id=20,
        expires_at="2030-01-02T00:00:00+00:00",
    )

    hits = repository.search([1.0, 0.0], "alice", 10, ["doc-a"], top_k=5)

    assert [hit.document_id for hit in hits] == ["doc-a", "doc-a"]
    assert hits[0].text == "alpha"
    assert hits[0].page_start == 1
    assert repository.search([1.0, 0.0], "bob", 10, ["doc-a"], 5) == []
    assert repository.search([1.0, 0.0], "alice", 20, ["doc-a"], 5) == []
    assert repository.search([1.0, 0.0], "alice", 10, ["doc-b"], 5) == []

    collection = repository.client.get_collection(repository.collection_name)
    stored = collection.get(where={"document_id": "doc-a"}, include=["metadatas"])
    metadata = stored["metadatas"][0]
    assert metadata["user_id"] == "alice"
    assert metadata["session_id"] == 10
    assert metadata["original_filename"] == "doc-a.pdf"
    assert metadata["expires_at"] == "2030-01-01T00:00:00+00:00"


def test_document_whitelist_excludes_unselected_chunks():
    repository = make_repository()
    for document_id, vector in (("selected", [1.0, 0.0]), ("other", [1.0, 0.0])):
        repository.upsert_document_chunks(
            [chunk(document_id, 0, document_id, 1)],
            [vector],
            user_id="alice",
            session_id=1,
            expires_at="2030-01-01T00:00:00+00:00",
        )

    hits = repository.search([1.0, 0.0], "alice", 1, ["selected"], top_k=10)

    assert [hit.document_id for hit in hits] == ["selected"]


def test_reindex_replaces_stale_tail_chunks_and_delete_is_idempotent():
    repository = make_repository()
    repository.upsert_document_chunks(
        [chunk("doc", 0, "zero", 1), chunk("doc", 1, "one", 2)],
        [[1.0, 0.0], [0.0, 1.0]],
        "alice",
        1,
        "2030-01-01T00:00:00Z",
    )
    repository.upsert_document_chunks(
        [chunk("doc", 0, "replacement", 1)],
        [[1.0, 0.0]],
        "alice",
        1,
        "2030-01-01T00:00:00Z",
    )

    assert repository.count_document("doc") == 1
    assert repository.search([1.0, 0.0], "alice", 1, ["doc"], 5)[0].text == "replacement"

    repository.delete_document("doc")
    repository.delete_document("doc")
    assert repository.count_document("doc") == 0


def test_upsert_rejects_embedding_count_mismatch():
    repository = make_repository()

    with pytest.raises(ValueError, match="same length"):
        repository.upsert_document_chunks(
            [chunk("doc", 0, "text", 1)],
            [],
            "alice",
            1,
            "2030-01-01T00:00:00+00:00",
        )
