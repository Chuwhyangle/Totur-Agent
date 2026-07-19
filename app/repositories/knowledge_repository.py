"""Chroma 学习笔记向量库访问层。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb

from app.services.knowledge_chunker import KnowledgeChunk
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_BATCH_SIZE,
    COLLECTION_PREFIX,
    KNOWLEDGE_COLLECTION_NAME,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class KnowledgeHit:
    """一次向量检索命中的学习笔记块。"""

    content: str
    source: str
    title_path: str
    similarity: float


@dataclass(frozen=True)
class KnowledgeEntry:
    """向量库里已经索引的一条学习笔记块。"""

    chunk_id: str
    content: str
    source: str
    title_path: str
    embedding: list[float] | None = None


class KnowledgeRepository:
    """隔离 Chroma API，让工具层不直接依赖具体向量库实现。"""

    def __init__(
        self,
        client: Any | None = None,
        collection_name: str = KNOWLEDGE_COLLECTION_NAME,
    ) -> None:
        """默认使用本地持久化 Chroma；测试可注入 EphemeralClient。"""

        self.client = client or chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )
        self.collection_name = collection_name

    def rebuild(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Replace the collection with the supplied chunks."""

        self._validate_write(chunks, embeddings)
        self._delete_collection_if_exists()
        collection = self._create_collection()
        return self._write(collection, "add", chunks, embeddings)

    def upsert(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Insert or replace chunks without rebuilding the collection."""

        self._validate_write(chunks, embeddings)
        if not chunks:
            return 0
        collection = self._get_collection()
        if collection is None:
            collection = self._create_collection()
        return self._write(collection, "upsert", chunks, embeddings)

    def delete(self, ids: list[str]) -> int:
        """Delete the specified chunk IDs from the live collection."""

        if not ids:
            return 0
        collection = self._get_collection()
        if collection is None:
            return 0
        for start in range(0, len(ids), EMBEDDING_BATCH_SIZE):
            collection.delete(ids=ids[start : start + EMBEDDING_BATCH_SIZE])
        return len(ids)

    @staticmethod
    def _validate_write(
        chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

    @staticmethod
    def _write(collection, method, chunks, embeddings) -> int:
        if not chunks:
            return 0
        created_at = datetime.now(timezone.utc).isoformat()
        write = getattr(collection, method)
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[start : start + EMBEDDING_BATCH_SIZE]
            write(
                ids=[chunk.chunk_id for chunk in batch_chunks],
                documents=[chunk.content for chunk in batch_chunks],
                embeddings=embeddings[start : start + EMBEDDING_BATCH_SIZE],
                metadatas=[
                    {
                        "source": chunk.source,
                        "title_path": chunk.title_path,
                        "created_at": created_at,
                        "subject": chunk.subject,
                    }
                    for chunk in batch_chunks
                ],
            )
        return len(chunks)

    def search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[KnowledgeHit]:
        """按向量相似度检索学习笔记块。"""

        if top_k <= 0:
            return []

        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        hits: list[KnowledgeHit] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            safe_metadata = metadata or {}
            hits.append(
                KnowledgeHit(
                    content=str(document or ""),
                    source=str(safe_metadata.get("source") or ""),
                    title_path=str(safe_metadata.get("title_path") or ""),
                    similarity=1 - float(distance or 0),
                )
            )

        return hits

    def count(self) -> int:
        """返回当前集合里的块数量；集合不存在时返回 0。"""

        collection = self._get_collection()
        if collection is None:
            return 0

        return int(collection.count())

    def list_entries(self, include_embeddings: bool = False) -> list[KnowledgeEntry]:
        """列出当前集合里的块；评测脚本用它做 corpus 对拍和 BM25 实验。"""

        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []

        include = ["documents", "metadatas"]
        if include_embeddings:
            include.append("embeddings")

        results = collection.get(include=include)
        ids = results.get("ids") or []
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        raw_embeddings = results.get("embeddings") if include_embeddings else None

        entries: list[KnowledgeEntry] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            safe_metadata = metadata or {}
            embedding = _embedding_at(raw_embeddings, index)
            entries.append(
                KnowledgeEntry(
                    chunk_id=str(chunk_id),
                    content=str(documents[index] if index < len(documents) else ""),
                    source=str(safe_metadata.get("source") or ""),
                    title_path=str(safe_metadata.get("title_path") or ""),
                    embedding=embedding,
                )
            )

        return entries

    def _create_collection(self):
        """创建 cosine 距离集合，避免 Chroma 默认 L2 影响阈值语义。"""

        return self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_collection(self):
        """获取集合；不存在时返回 None，让调用方走结构化错误。"""

        try:
            return self.client.get_collection(self.collection_name)
        except Exception:
            return None

    def _delete_collection_if_exists(self) -> None:
        """删除旧集合；首次构建时集合不存在是正常情况。"""

        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            return


def _embedding_at(raw_embeddings: Any, index: int) -> list[float] | None:
    """从 Chroma 返回值中安全取出某个 embedding。"""

    if raw_embeddings is None:
        return None

    try:
        embedding = raw_embeddings[index]
    except (IndexError, TypeError):
        return None

    if embedding is None:
        return None

    return [float(value) for value in embedding]


def list_knowledge_collections(client: Any) -> list[str]:
    """List logical subject-shard collections in deterministic order."""

    names: list[str] = []
    for item in client.list_collections():
        name = getattr(item, "name", item)
        if isinstance(name, str) and name.startswith(COLLECTION_PREFIX):
            names.append(name)
    return sorted(set(names))
