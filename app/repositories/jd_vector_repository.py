"""Chroma repository for public JD child vectors."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb

from app.repositories.knowledge_repository import KnowledgeEntry, KnowledgeHit
from app.services.jd_corpus import JDChildDocument
from app.services.rag_settings import CHROMA_PERSIST_DIR


JD_COLLECTION_NAME = "job_descriptions"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class JDVectorRepository:
    """Store and query JD children without changing learning-note storage."""

    def __init__(
        self,
        client: Any | None = None,
        collection_name: str = JD_COLLECTION_NAME,
    ) -> None:
        self.client = client or chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )
        self.collection_name = collection_name

    def rebuild(
        self,
        children: list[JDChildDocument],
        embeddings: list[list[float]],
    ) -> int:
        self._validate_write(children, embeddings)
        self._delete_collection_if_exists()
        collection = self._create_collection()
        return self._write(collection, "add", children, embeddings)

    def upsert(
        self,
        children: list[JDChildDocument],
        embeddings: list[list[float]],
    ) -> int:
        self._validate_write(children, embeddings)
        if not children:
            return 0
        collection = self._get_collection() or self._create_collection()
        return self._write(collection, "upsert", children, embeddings)

    def delete(self, ids: list[str]) -> int:
        if not ids:
            return 0
        collection = self._get_collection()
        if collection is None:
            return 0
        collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        collection = self._get_collection()
        return int(collection.count()) if collection is not None else 0

    def snapshot_hashes(self) -> dict[str, str]:
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return {}
        results = collection.get(include=["metadatas"])
        ids = results.get("ids") or []
        metadatas = results.get("metadatas") or []
        return {
            str(child_id): str(
                (metadatas[index] or {}).get("index_sha256") or ""
            )
            for index, child_id in enumerate(ids)
            if index < len(metadatas)
        }


    def search(
        self,
        query_embedding: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeHit]:
        if top_k <= 0:
            return []
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        results = collection.query(**kwargs)
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
                    title_path=str(safe_metadata.get("child_type") or ""),
                    similarity=1 - float(distance or 0),
                )
            )
        return hits

    def list_entries(
        self,
        include_embeddings: bool = False,
        where: dict[str, Any] | None = None,
    ) -> list[KnowledgeEntry]:
        collection = self._get_collection()
        if collection is None or collection.count() == 0:
            return []
        kwargs: dict[str, Any] = {
            "include": ["documents", "metadatas"]
            + (["embeddings"] if include_embeddings else [])
        }
        if where:
            kwargs["where"] = where
        results = collection.get(**kwargs)
        ids = results.get("ids") or []
        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        raw_embeddings = results.get("embeddings") if include_embeddings else None
        entries: list[KnowledgeEntry] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            safe_metadata = metadata or {}
            embedding = None
            if raw_embeddings is not None and index < len(raw_embeddings):
                vector = raw_embeddings[index]
                embedding = list(vector) if vector is not None else None
            entries.append(
                KnowledgeEntry(
                    chunk_id=str(chunk_id),
                    content=str(documents[index] if index < len(documents) else ""),
                    source=str(safe_metadata.get("source") or ""),
                    title_path=str(safe_metadata.get("child_type") or ""),
                    embedding=embedding,
                )
            )
        return entries

    @staticmethod
    def _validate_write(
        children: list[JDChildDocument], embeddings: list[list[float]]
    ) -> None:
        if len(children) != len(embeddings):
            raise ValueError("children and embeddings must have the same length")
        ids = [child.child_id for child in children]
        if len(ids) != len(set(ids)):
            raise ValueError("JD child IDs must be unique")

    @staticmethod
    def _write(collection, method, children, embeddings) -> int:
        if not children:
            return 0
        created_at = datetime.now(timezone.utc).isoformat()
        getattr(collection, method)(
            ids=[child.child_id for child in children],
            documents=[child.content for child in children],
            embeddings=embeddings,
            metadatas=[
                {
                    **child.metadata,
                    "child_type": child.child_type,
                    "index_sha256": child.index_sha256,
                    "created_at": created_at,
                }
                for child in children
            ],
        )
        return len(children)

    def _create_collection(self):
        return self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_collection(self):
        try:
            return self.client.get_collection(self.collection_name)
        except Exception:
            return None

    def _delete_collection_if_exists(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
