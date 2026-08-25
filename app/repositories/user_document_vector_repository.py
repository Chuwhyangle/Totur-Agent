"""Chroma repository for the persistent user-document collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from app.repositories.knowledge_repository import KnowledgeEntry
from app.services.knowledge_chunker import KnowledgeChunk
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    EMBEDDING_BATCH_SIZE,
    USER_DOCUMENT_COLLECTION_NAME,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class UserDocumentHit:
    """A chunk returned from the user-document collection."""

    chunk_id: str
    document_id: str
    content: str
    source: str
    title_path: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    similarity: float


class UserDocumentVectorRepository:
    """Persist and query user-uploaded chunks in an isolated Chroma collection."""

    def __init__(
        self,
        client: Any | None = None,
        collection_name: str = USER_DOCUMENT_COLLECTION_NAME,
    ) -> None:
        self.client = client or chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )
        self.collection_name = collection_name

    def upsert_document_chunks(
        self,
        *,
        document_id: str,
        user_id: str,
        original_filename: str,
        version_no: int,
        chunks: list[KnowledgeChunk],
        page_ranges: list[tuple[int | None, int | None]],
        embeddings: list[list[float]],
    ) -> int:
        if not user_id or not user_id.strip():
            raise ValueError("user_id must not be empty")
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if len(chunks) != len(page_ranges):
            raise ValueError("chunks and page_ranges must have the same length")
        if not chunks:
            return 0

        collection = self._get_or_create_collection()
        # Delete first so retries with fewer chunks cannot leave stale tail data.
        collection.delete(where={"document_id": document_id})
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            batch_ranges = page_ranges[start : start + EMBEDDING_BATCH_SIZE]
            metadatas = []
            for chunk, page_range in zip(batch, batch_ranges):
                page_start, page_end = page_range
                metadata: dict[str, Any] = {
                    "user_id": user_id,
                    "document_id": document_id,
                    "original_filename": original_filename,
                    "title_path": chunk.title_path,
                    "chunk_index": int(chunk.chunk_index),
                    "version_no": int(version_no),
                }
                if page_start is not None:
                    metadata["page_start"] = int(page_start)
                if page_end is not None:
                    metadata["page_end"] = int(page_end)
                metadatas.append(metadata)

            collection.upsert(
                ids=[f"{document_id}#{chunk.chunk_index}" for chunk in batch],
                documents=[chunk.content for chunk in batch],
                embeddings=embeddings[start : start + EMBEDDING_BATCH_SIZE],
                metadatas=metadatas,
            )
        return len(chunks)

    def search(
        self,
        query_embedding: list[float],
        user_id: str | int = "default",
        top_k: int | None = None,
        document_ids: list[str] | None = None,
    ) -> list[UserDocumentHit]:
        # Keep the explicit ``search(embedding, user_id, top_k)`` API while
        # also satisfying hybrid retrieval's repository protocol, which calls
        # ``search(query_embedding=..., top_k=...)`` without a user id.
        if top_k is None and isinstance(user_id, int):
            top_k = user_id
            user_id = "default"
        if top_k is None:
            return []
        if top_k <= 0 or not user_id or not user_id.strip():
            return []
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []

        clauses: list[dict[str, Any]] = [{"user_id": {"$eq": user_id}}]
        allowed = list(dict.fromkeys(document_ids or []))
        if allowed:
            clauses.append({"document_id": {"$in": allowed}})
        where: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$and": clauses}
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[UserDocumentHit] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            distance = float(distances[index]) if index < len(distances) else 1.0
            hits.append(
                UserDocumentHit(
                    chunk_id=str(chunk_id),
                    document_id=str(metadata.get("document_id") or ""),
                    content=str(documents[index] if index < len(documents) else ""),
                    source=str(metadata.get("original_filename") or ""),
                    title_path=str(metadata.get("title_path") or ""),
                    chunk_index=int(metadata.get("chunk_index") or 0),
                    page_start=_optional_int(metadata.get("page_start")),
                    page_end=_optional_int(metadata.get("page_end")),
                    similarity=1.0 - distance,
                )
            )
        hits.sort(key=lambda hit: hit.similarity, reverse=True)
        return hits

    def delete_document(self, document_id: str) -> None:
        if not document_id:
            return
        collection = self._get_collection()
        if collection is not None:
            collection.delete(where={"document_id": document_id})

    def count_document(self, document_id: str) -> int:
        if not document_id:
            return 0
        collection = self._get_collection()
        if collection is None:
            return 0
        return len(collection.get(where={"document_id": document_id}, include=[]).get("ids") or [])

    def count(self) -> int:
        collection = self._get_collection()
        return int(collection.count()) if collection is not None else 0

    def list_entries(self, include_embeddings: bool = False) -> list[KnowledgeEntry]:
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []
        include = ["documents", "metadatas"]
        if include_embeddings:
            include.append("embeddings")
        result = collection.get(include=include)
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        embeddings = result.get("embeddings") if include_embeddings else None
        return [
            KnowledgeEntry(
                chunk_id=str(chunk_id),
                content=str(documents[index] if index < len(documents) else ""),
                source=str((metadatas[index] or {}).get("original_filename") or ""),
                title_path=str((metadatas[index] or {}).get("title_path") or ""),
                embedding=(
                    [float(value) for value in embeddings[index]]
                    if embeddings is not None and index < len(embeddings) and embeddings[index] is not None
                    else None
                ),
            )
            for index, chunk_id in enumerate(ids)
        ]

    def _get_or_create_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_collection(self):
        try:
            return self.client.get_collection(self.collection_name)
        except NotFoundError:
            return None


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None
