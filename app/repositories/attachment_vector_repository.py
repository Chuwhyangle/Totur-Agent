"""Chroma repository for session-scoped temporary attachment chunks."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from app.services.documents.attachment_chunker import AttachmentChunk
from app.services.rag_settings import CHROMA_PERSIST_DIR, EMBEDDING_BATCH_SIZE


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ATTACHMENT_COLLECTION_NAME = "temporary_document_chunks"


@dataclass(frozen=True, slots=True)
class AttachmentVectorHit:
    chunk_id: str
    document_id: str
    text: str
    original_filename: str
    chunk_index: int
    page_start: int
    page_end: int
    similarity: float
    locator_unit: str = "page"
    locator: str | None = None


class AttachmentVectorRepository:
    """Enforce user/session/document filters inside the Chroma boundary."""

    def __init__(
        self,
        client: Any | None = None,
        collection_name: str = ATTACHMENT_COLLECTION_NAME,
    ) -> None:
        self.client = client or chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )
        self.collection_name = collection_name

    def upsert_document_chunks(
        self,
        chunks: list[AttachmentChunk],
        embeddings: list[list[float]],
        user_id: str,
        session_id: int,
        expires_at: datetime | str,
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return 0
        if not user_id or not user_id.strip():
            raise ValueError("user_id must not be empty")
        document_id = chunks[0].document_id
        if not document_id or any(
            chunk.document_id != document_id for chunk in chunks
        ):
            raise ValueError("all chunks must belong to one document")
        normalized_expires_at = _normalize_utc_iso(expires_at)

        collection = self._get_or_create_collection()
        # Deterministic IDs make writes idempotent, while this delete also removes
        # stale tail chunks if a retry produces fewer chunks.
        collection.delete(where={"document_id": document_id})
        created_at = datetime.now(timezone.utc).isoformat()
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                documents=[chunk.text for chunk in batch],
                embeddings=embeddings[start : start + EMBEDDING_BATCH_SIZE],
                metadatas=[
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "document_id": chunk.document_id,
                        "original_filename": chunk.original_filename,
                        "chunk_index": chunk.chunk_index,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "locator_unit": chunk.locator_unit,
                        "created_at": created_at,
                        "expires_at": normalized_expires_at,
                        **({"locator": chunk.locator} if chunk.locator else {}),
                    }
                    for chunk in batch
                ],
            )
        return len(chunks)

    def search(
        self,
        query_embedding: list[float],
        user_id: str,
        session_id: int,
        document_ids: list[str],
        top_k: int,
    ) -> list[AttachmentVectorHit]:
        if top_k <= 0 or not document_ids:
            return []
        allowed_document_ids = list(dict.fromkeys(document_ids))
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            where={
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"session_id": {"$eq": session_id}},
                    {"document_id": {"$in": allowed_document_ids}},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )
        ids = (results.get("ids") or [[]])[0]
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        hits: list[AttachmentVectorHit] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            document_id = str(metadata.get("document_id") or "")
            if document_id not in allowed_document_ids:
                continue
            distance = float(distances[index]) if index < len(distances) else 1.0
            hits.append(
                AttachmentVectorHit(
                    chunk_id=str(chunk_id),
                    document_id=document_id,
                    text=str(documents[index] if index < len(documents) else ""),
                    original_filename=str(
                        metadata.get("original_filename") or ""
                    ),
                    chunk_index=int(metadata.get("chunk_index") or 0),
                    page_start=int(metadata.get("page_start") or 0),
                    page_end=int(metadata.get("page_end") or 0),
                    similarity=1.0 - distance,
                    locator_unit=str(metadata.get("locator_unit") or "page"),
                    locator=(
                        str(metadata["locator"])
                        if metadata.get("locator") is not None
                        else None
                    ),
                )
            )
        hits.sort(key=lambda item: item.similarity, reverse=True)
        return hits

    def delete_document(self, document_id: str) -> None:
        if not document_id:
            return
        collection = self._get_collection()
        if collection is None:
            return
        collection.delete(where={"document_id": document_id})

    def count_document(self, document_id: str) -> int:
        if not document_id:
            return 0
        collection = self._get_collection()
        if collection is None:
            return 0
        result = collection.get(
            where={"document_id": document_id},
            include=[],
        )
        return len(result.get("ids") or [])

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


def _normalize_utc_iso(value: datetime | str) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ValueError("expires_at must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("expires_at must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat()
