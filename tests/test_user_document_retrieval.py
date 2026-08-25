"""专项测试：user_documents 与学习笔记检索融合。"""

from dataclasses import dataclass

import app.services.agent.tools.search_learning_notes as search
from app.repositories.knowledge_repository import KnowledgeHit
from app.repositories.user_document_vector_repository import UserDocumentHit


@dataclass
class NoteRepository:
    hits: list[KnowledgeHit]

    def __post_init__(self):
        self.search_calls = 0
        self.collection_name = "learning_notes"

    def count(self):
        return len(self.hits)

    def search(self, query_embedding, top_k):
        self.search_calls += 1
        return self.hits[:top_k]

    def list_entries(self, include_embeddings=False):
        return []


class UserRepository:
    def __init__(self, hits=None, error=None):
        self.hits = hits or []
        self.error = error
        self.search_calls = 0
        self.collection_name = "user_documents"

    def count(self):
        return len(self.hits)

    def list_entries(self, include_embeddings=False):
        return []

    def search(self, query_embedding, user_id, top_k, document_ids=None):
        self.search_calls += 1
        if self.error:
            raise self.error
        return self.hits[:top_k]


def note(content="note", similarity=0.8):
    return KnowledgeHit(content=content, source="notes.md", title_path="Notes", similarity=similarity)


def user(content="upload", similarity=0.9, page_start=2, page_end=3):
    return UserDocumentHit(
        chunk_id="doc#0",
        document_id="doc",
        content=content,
        source="upload.md",
        title_path="Guide",
        chunk_index=0,
        page_start=page_start,
        page_end=page_end,
        similarity=similarity,
    )


def test_flag_off_does_not_query_user_documents(monkeypatch):
    notes = NoteRepository([note()])
    users = UserRepository([user()])
    monkeypatch.setattr(search, "ENABLE_USER_DOCUMENT_RETRIEVAL", False)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "_get_user_document_repository", lambda: users)

    hits = search._retrieve_hits(
        repository=notes,
        query="q",
        query_embedding=[1.0],
        top_k=3,
    )

    assert len(hits) == 1
    assert users.search_calls == 0


def test_flag_on_merges_and_sorts_by_similarity(monkeypatch):
    notes = NoteRepository([note(similarity=0.8)])
    users = UserRepository([user(similarity=0.95)])
    monkeypatch.setattr(search, "ENABLE_USER_DOCUMENT_RETRIEVAL", True)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "_get_user_document_repository", lambda: users)

    hits = search._retrieve_hits(repository=notes, query="q", query_embedding=[1.0], top_k=2)

    assert [hit.source for hit in hits] == ["upload.md", "notes.md"]


def test_flag_on_with_empty_user_collection_degrades_gracefully(monkeypatch):
    notes = NoteRepository([note()])
    users = UserRepository([])
    monkeypatch.setattr(search, "ENABLE_USER_DOCUMENT_RETRIEVAL", True)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "_get_user_document_repository", lambda: users)

    hits = search._retrieve_hits(repository=notes, query="q", query_embedding=[1.0], top_k=3)

    assert len(hits) == 1
    assert users.search_calls == 0


def test_notes_branch_failure_still_returns_user_document_hits(monkeypatch):
    class BrokenNotes(NoteRepository):
        def search(self, query_embedding, top_k):
            raise RuntimeError("notes unavailable")

    users = UserRepository([user()])
    monkeypatch.setattr(search, "ENABLE_USER_DOCUMENT_RETRIEVAL", True)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "_get_user_document_repository", lambda: users)

    hits = search._retrieve_hits(repository=BrokenNotes([note()]), query="q", query_embedding=[1.0], top_k=3)

    assert [hit.source for hit in hits] == ["upload.md"]


def test_user_document_branch_failure_still_returns_note_hits(monkeypatch):
    notes = NoteRepository([note()])
    users = UserRepository([user()], error=RuntimeError("user docs unavailable"))
    monkeypatch.setattr(search, "ENABLE_USER_DOCUMENT_RETRIEVAL", True)
    monkeypatch.setattr(search, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(search, "_get_user_document_repository", lambda: users)

    hits = search._retrieve_hits(repository=notes, query="q", query_embedding=[1.0], top_k=3)

    assert [hit.source for hit in hits] == ["notes.md"]


def test_user_upload_items_carry_doc_type_and_page_range():
    item = search._item_from_hit(search._hit_from_user_document(user(page_start=12, page_end=12)))

    assert item["doc_type"] == "user_upload"
    assert item["page_range"] == "p.12"


def test_note_items_shape_is_unchanged():
    item = search._item_from_hit(note())

    assert set(item) == {
        "title", "content", "source", "title_path", "similarity",
        "match_score", "raw_text_excerpt",
    }
