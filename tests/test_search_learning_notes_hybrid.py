"""Tests for hybrid retrieval routing in search_learning_notes."""

from __future__ import annotations

import logging

import chromadb

from app.repositories.knowledge_repository import KnowledgeHit, KnowledgeRepository
from app.services.agent.tools import search_learning_notes as tool_module
from app.services.agent.tools.search_learning_notes import search_learning_notes
from app.services.knowledge_chunker import KnowledgeChunk


class FakeEmbeddingClient:
    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors.get(text, [0.0, 0.0]) for text in texts]


def _chunk(index: int, content: str, title_path: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        content=content,
        source=f"docs/note-{index}.md",
        title_path=title_path,
        chunk_index=index,
    )


def _repository() -> KnowledgeRepository:
    repository = KnowledgeRepository(client=chromadb.EphemeralClient())
    repository._delete_collection_if_exists()
    return repository


def _seed_repo(monkeypatch) -> KnowledgeRepository:
    repository = _repository()
    repository.rebuild(
        chunks=[
            _chunk(0, "FastAPI 路由说明 Hybrid BM25", "FastAPI > 路由"),
            _chunk(1, "SQLite 表结构说明", "SQLite > 表"),
        ],
        embeddings=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
    )
    monkeypatch.setattr(tool_module, "_repository", repository)
    monkeypatch.setattr(
        tool_module,
        "_embedding_client",
        FakeEmbeddingClient({"FastAPI Hybrid BM25": [1.0, 0.0]}),
    )
    monkeypatch.setattr(tool_module, "_manifest_cache", None)
    return repository


def test_search_learning_notes_uses_hybrid_when_flag_enabled(monkeypatch):
    _seed_repo(monkeypatch)
    monkeypatch.setattr(tool_module, "ENABLE_HYBRID_RETRIEVAL", True)
    monkeypatch.setattr(tool_module, "_get_manifest_fingerprint", lambda: "fp-test")

    calls: list[dict] = []

    def fake_hybrid_search(**kwargs):
        calls.append(kwargs)
        return [
            KnowledgeHit(
                content="FastAPI 路由说明 Hybrid BM25",
                source="docs/note-0.md",
                title_path="FastAPI > 路由",
                similarity=0.95,
            )
        ]

    monkeypatch.setattr(tool_module, "hybrid_search", fake_hybrid_search)

    result = search_learning_notes("FastAPI Hybrid BM25", limit=3)

    assert result["ok"] is True
    assert result["found"] is True
    assert result["count"] == 1
    assert result["results"] == result["items"]
    assert result["results"][0]["title"] == "FastAPI > 路由"
    assert result["summary"] == {"returned_count": 1}
    assert len(calls) == 1
    assert calls[0]["fingerprint"] == "fp-test"
    assert calls[0]["query"] == "FastAPI Hybrid BM25"
    assert calls[0]["top_k"] == 3


def test_search_learning_notes_uses_vector_when_flag_disabled(monkeypatch):
    repository = _seed_repo(monkeypatch)
    monkeypatch.setattr(tool_module, "ENABLE_HYBRID_RETRIEVAL", False)

    hybrid_calls: list[dict] = []
    search_calls: list[dict] = []

    def fake_hybrid_search(**kwargs):
        hybrid_calls.append(kwargs)
        return []

    original_search = repository.search

    def tracking_search(*, query_embedding, top_k):
        search_calls.append({"top_k": top_k})
        return original_search(query_embedding=query_embedding, top_k=top_k)

    monkeypatch.setattr(tool_module, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(repository, "search", tracking_search)

    result = search_learning_notes("FastAPI Hybrid BM25", limit=2)

    assert result["ok"] is True
    assert result["found"] is True
    assert hybrid_calls == []
    assert search_calls == [{"top_k": 2}]


def test_search_learning_notes_falls_back_when_manifest_missing(monkeypatch):
    repository = _seed_repo(monkeypatch)
    monkeypatch.setattr(tool_module, "ENABLE_HYBRID_RETRIEVAL", True)
    monkeypatch.setattr(tool_module, "_get_manifest_fingerprint", lambda: None)

    hybrid_calls: list[dict] = []
    search_calls: list[dict] = []

    def fake_hybrid_search(**kwargs):
        hybrid_calls.append(kwargs)
        return []

    original_search = repository.search

    def tracking_search(*, query_embedding, top_k):
        search_calls.append({"top_k": top_k})
        return original_search(query_embedding=query_embedding, top_k=top_k)

    monkeypatch.setattr(tool_module, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(repository, "search", tracking_search)

    result = search_learning_notes("FastAPI Hybrid BM25")

    assert result["ok"] is True
    assert result["found"] is True
    assert hybrid_calls == []
    assert len(search_calls) == 1


def test_get_manifest_fingerprint_returns_none_when_file_missing(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(tool_module, "_manifest_cache", None)

    with caplog.at_level(logging.WARNING, logger=tool_module.__name__):
        fingerprint = tool_module._get_manifest_fingerprint()

    assert fingerprint is None
    assert "index manifest missing" in caplog.text


def test_get_manifest_fingerprint_returns_none_on_invalid_manifest(
    monkeypatch, tmp_path, caplog
):
    path = tmp_path / "index_manifest.json"
    path.write_text("{not-valid-json", encoding="utf-8")
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", path)
    monkeypatch.setattr(tool_module, "_manifest_cache", None)

    with caplog.at_level(logging.WARNING, logger=tool_module.__name__):
        fingerprint = tool_module._get_manifest_fingerprint()

    assert fingerprint is None
    assert "index manifest invalid" in caplog.text


def test_get_manifest_fingerprint_caches_by_mtime(monkeypatch, tmp_path):
    from app.services.index_manifest import (
        CorpusFileManifest,
        IndexManifest,
        write_manifest,
    )

    path = tmp_path / "index_manifest.json"
    manifest = IndexManifest.create(
        schema_version=1,
        collection_name="learning_notes",
        built_at="2026-01-01T00:00:00Z",
        embedding_model="test-model",
        embedding_dimensions=2,
        chunk_size=512,
        chunk_overlap=50,
        corpus_root="docs",
        files=[
            CorpusFileManifest(
                path="docs/a.md",
                content_sha256="a" * 64,
                chunk_count=1,
            )
        ],
    )
    write_manifest(path, manifest)
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", path)
    monkeypatch.setattr(tool_module, "_manifest_cache", None)

    first = tool_module._get_manifest_fingerprint()
    second = tool_module._get_manifest_fingerprint()

    assert first == manifest.fingerprint
    assert second == first
    assert tool_module._manifest_cache is not None
    assert tool_module._manifest_cache[1] == first


def test_search_learning_notes_filters_hybrid_scores_by_threshold(monkeypatch):
    _seed_repo(monkeypatch)
    monkeypatch.setattr(tool_module, "ENABLE_HYBRID_RETRIEVAL", True)
    monkeypatch.setattr(tool_module, "_get_manifest_fingerprint", lambda: "fp-test")
    monkeypatch.setattr(tool_module, "SIMILARITY_THRESHOLD", 0.45)

    def fake_hybrid_search(**kwargs):
        return [
            KnowledgeHit(
                content="strong lexical hit",
                source="docs/note-0.md",
                title_path="FastAPI > 路由",
                similarity=0.8,
            ),
            KnowledgeHit(
                content="weak hit",
                source="docs/note-1.md",
                title_path="SQLite > 表",
                similarity=0.2,
            ),
        ]

    monkeypatch.setattr(tool_module, "hybrid_search", fake_hybrid_search)

    result = search_learning_notes("FastAPI Hybrid BM25")

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["source"] == "docs/note-0.md"
    assert result["results"][0]["similarity"] == 0.8
    assert result["items"][0]["match_score"] == 80
