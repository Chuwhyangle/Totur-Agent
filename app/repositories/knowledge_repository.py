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


class KnowledgeRepository:
    """隔离 Chroma API，让工具层不直接依赖具体向量库实现。"""

    def __init__(self, client: Any | None = None) -> None:
        """默认使用本地持久化 Chroma；测试可注入 EphemeralClient。"""

        self.client = client or chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )

    def rebuild(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int:
        """删除并重建学习笔记集合，返回写入的块数量。"""

        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        self._delete_collection_if_exists()
        collection = self._create_collection()
        if not chunks:
            return 0

        created_at = datetime.now(timezone.utc).isoformat()
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[start : start + EMBEDDING_BATCH_SIZE]
            batch_embeddings = embeddings[start : start + EMBEDDING_BATCH_SIZE]
            collection.add(
                ids=[chunk.chunk_id for chunk in batch_chunks],
                documents=[chunk.content for chunk in batch_chunks],
                embeddings=batch_embeddings,
                metadatas=[
                    {
                        "source": chunk.source,
                        "title_path": chunk.title_path,
                        "created_at": created_at,
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

    def _create_collection(self):
        """创建 cosine 距离集合，避免 Chroma 默认 L2 影响阈值语义。"""

        return self.client.create_collection(
            name=KNOWLEDGE_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_collection(self):
        """获取集合；不存在时返回 None，让调用方走结构化错误。"""

        try:
            return self.client.get_collection(KNOWLEDGE_COLLECTION_NAME)
        except Exception:
            return None

    def _delete_collection_if_exists(self) -> None:
        """删除旧集合；首次构建时集合不存在是正常情况。"""

        try:
            self.client.delete_collection(KNOWLEDGE_COLLECTION_NAME)
        except Exception:
            return

