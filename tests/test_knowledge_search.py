"""学习笔记向量库和检索工具的测试。"""

from __future__ import annotations

import chromadb

from app.clients.embedding_client import EmbeddingError
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.agent.tools import search_learning_notes as tool_module
from app.services.agent.tools.search_learning_notes import search_learning_notes
from app.services.knowledge_chunker import KnowledgeChunk


class FakeEmbeddingClient:
    """按文本返回固定向量，避免测试依赖真实 embedding API。"""

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors.get(text, [0.0, 0.0]) for text in texts]


class FailingEmbeddingClient:
    """模拟 embedding API 故障。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("provider down")


def _chunk(index: int, content: str, title_path: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        content=content,
        source=f"docs/note-{index}.md",
        title_path=title_path,
        chunk_index=index,
    )


def _repository() -> KnowledgeRepository:
    """创建干净的测试 repository，避免 EphemeralClient 复用集合污染用例。"""

    repository = KnowledgeRepository(client=chromadb.EphemeralClient())
    repository._delete_collection_if_exists()
    return repository


def test_knowledge_repository_rebuild_search_and_count():
    repository = _repository()
    chunks = [
        _chunk(0, "FastAPI 路由把 URL 绑定到函数。", "FastAPI > 路由"),
        _chunk(1, "SQLite 是本地轻量数据库。", "SQLite > 基础"),
        _chunk(2, "滚动摘要用于压缩较早历史。", "记忆系统 > 滚动摘要"),
    ]

    count = repository.rebuild(
        chunks=chunks,
        embeddings=[
            [1.0, 0.0],
            [0.0, 1.0],
            [0.8, 0.2],
        ],
    )
    hits = repository.search(query_embedding=[1.0, 0.0], top_k=2)

    assert count == 3
    assert repository.count() == 3
    assert [hit.title_path for hit in hits] == [
        "FastAPI > 路由",
        "记忆系统 > 滚动摘要",
    ]
    assert hits[0].source == "docs/note-0.md"
    assert hits[0].similarity >= hits[1].similarity


def test_knowledge_repository_rebuild_is_idempotent():
    repository = _repository()
    chunks = [_chunk(0, "第一次内容", "标题")]

    repository.rebuild(chunks=chunks, embeddings=[[1.0, 0.0]])
    repository.rebuild(chunks=chunks, embeddings=[[1.0, 0.0]])

    assert repository.count() == 1


def test_knowledge_repository_count_returns_zero_when_collection_missing():
    repository = _repository()

    assert repository.count() == 0


def test_search_learning_notes_returns_ranked_hits(monkeypatch):
    repository = _repository()
    repository.rebuild(
        chunks=[
            _chunk(0, "FastAPI 路由说明", "FastAPI > 路由"),
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
        FakeEmbeddingClient({"FastAPI": [1.0, 0.0]}),
    )

    result = search_learning_notes("FastAPI", limit=3)

    assert result["ok"] is True
    assert result["found"] is True
    assert result["count"] == 1
    assert result["results"] == result["items"]
    assert result["results"][0]["title"] == "FastAPI > 路由"
    assert result["results"][0]["source"] == "docs/note-0.md"
    assert result["results"][0]["similarity"] >= 0.99
    assert result["summary"] == {"returned_count": 1}


def test_search_learning_notes_applies_similarity_threshold(monkeypatch):
    repository = _repository()
    repository.rebuild(
        chunks=[_chunk(0, "SQLite 表结构说明", "SQLite > 表")],
        embeddings=[[0.0, 1.0]],
    )
    monkeypatch.setattr(tool_module, "_repository", repository)
    monkeypatch.setattr(
        tool_module,
        "_embedding_client",
        FakeEmbeddingClient({"FastAPI": [1.0, 0.0]}),
    )

    result = search_learning_notes("FastAPI", limit=3)

    assert result["ok"] is True
    assert result["found"] is False
    assert result["results"] == []
    assert result["items"] == []
    assert result["message"] == "未找到相关笔记。"


def test_search_learning_notes_rejects_empty_query():
    result = search_learning_notes("   ")

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "query must be a non-empty string.",
    }


def test_search_learning_notes_reports_index_not_built(monkeypatch):
    repository = _repository()
    monkeypatch.setattr(tool_module, "_repository", repository)

    result = search_learning_notes("记忆分层")

    assert result["ok"] is False
    assert result["error"] == "index_not_built"
    assert "build_knowledge_index.py" in result["message"]


def test_search_learning_notes_reports_embedding_failure(monkeypatch):
    repository = _repository()
    repository.rebuild(
        chunks=[_chunk(0, "FastAPI 路由说明", "FastAPI > 路由")],
        embeddings=[[1.0, 0.0]],
    )
    monkeypatch.setattr(tool_module, "_repository", repository)
    monkeypatch.setattr(tool_module, "_embedding_client", FailingEmbeddingClient())

    result = search_learning_notes("FastAPI")

    assert result["ok"] is False
    assert result["error"] == "embedding_failed"
