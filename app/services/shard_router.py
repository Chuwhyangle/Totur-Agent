"""Logical per-subject shard routing for single-machine Chroma.

Each ``learning_notes_<slug>`` collection is an independent logical shard.
Broadcast retrieval fans out synchronously through a thread pool, then merges
local top-k results. Hybrid BM25 scores are normalized against each shard's
local maximum, so they are not strictly comparable across shards; this is the
query-then-fetch trade-off accepted for this single-machine design. Pure vector
scores remain globally comparable because every shard uses cosine distance and
the same embedding model.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

from app.repositories.knowledge_repository import (
    KnowledgeHit,
    KnowledgeRepository,
    list_knowledge_collections,
)
from app.services.hybrid_retriever import BM25IndexCache, hybrid_search
from app.services.index_manifest import ManifestError, load_manifest
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    COLLECTION_PREFIX,
    ENABLE_HYBRID_RETRIEVAL,
    subject_slug,
    validate_subject_slug,
)

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ShardHandle:
    subject: str
    repository: KnowledgeRepository
    fingerprint: str | None = None


class ShardRouter:
    """Route known subjects and scatter-gather unknown/broadcast queries."""

    def __init__(self, shards: list[ShardHandle], *, bm25_cache: BM25IndexCache | None = None):
        self.shards = tuple(shards)
        self._by_subject = {shard.subject: shard for shard in self.shards}
        self._bm25_cache = bm25_cache or BM25IndexCache()

    @property
    def handles(self) -> tuple[ShardHandle, ...]:
        return self.shards

    @classmethod
    def from_client(
        cls,
        client: Any | None = None,
        *,
        manifest_dir: Path | None = None,
    ) -> "ShardRouter":
        if client is None:
            client = KnowledgeRepository().client
        manifest_root = manifest_dir or (PROJECT_ROOT / CHROMA_PERSIST_DIR)
        handles: list[ShardHandle] = []
        embedding_models: set[str] = set()
        for collection_name in list_knowledge_collections(client):
            slug = collection_name[len(COLLECTION_PREFIX) :]
            validate_subject_slug(slug)
            repository = KnowledgeRepository(client=client, collection_name=collection_name)
            metadata = getattr(repository._get_collection(), "metadata", None)
            if not isinstance(metadata, dict) or metadata.get("hnsw:space") != "cosine":
                raise ValueError(
                    f"collection {collection_name!r} must use hnsw:space=cosine"
                )
            manifest_path = manifest_root / f"index_manifest_{slug}.json"
            fingerprint: str | None = None
            if not manifest_path.exists():
                manifest = None
            else:
                manifest = load_manifest(manifest_path)
            if manifest is not None:
                if manifest.collection_name != collection_name:
                    raise ManifestError(
                        f"manifest collection {manifest.collection_name!r} does not match {collection_name!r}"
                    )
                embedding_models.add(manifest.embedding_model)
                fingerprint = manifest.fingerprint
            handles.append(ShardHandle(slug, repository, fingerprint))

        if len(embedding_models) > 1:
            raise ValueError(
                "all subject shard manifests must use the same embedding_model: "
                + ", ".join(sorted(embedding_models))
            )
        return cls(handles)

    def search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
        subject: str | None = None,
    ) -> list[KnowledgeHit]:
        if top_k <= 0 or not self.shards:
            return []

        if subject is not None:
            try:
                canonical_subject = subject_slug(subject)
            except ValueError:
                canonical_subject = subject.strip() if isinstance(subject, str) else ""
            shard = self._by_subject.get(canonical_subject)
            if shard is not None:
                return self._safe_search_shard(shard, query, query_embedding, top_k)
            logger.warning("unknown subject %r; falling back to broadcast retrieval", subject)

        return self._broadcast(query, query_embedding, top_k)

    def _broadcast(self, query: str, query_embedding: list[float], top_k: int) -> list[KnowledgeHit]:
        results: list[KnowledgeHit] = []
        max_workers = min(len(self.shards), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._safe_search_shard, shard, query, query_embedding, top_k): shard
                for shard in self.shards
            }
            for future in as_completed(futures):
                results.extend(future.result())
        return sorted(
            results,
            key=lambda hit: (-hit.similarity, hit.source, hit.title_path, hit.content),
        )[:top_k]

    def _safe_search_shard(
        self,
        shard: ShardHandle,
        query: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[KnowledgeHit]:
        try:
            if ENABLE_HYBRID_RETRIEVAL and shard.fingerprint:
                return hybrid_search(
                    repository=shard.repository,
                    query=query,
                    query_embedding=query_embedding,
                    top_k=top_k,
                    fingerprint=shard.fingerprint,
                    cache=self._bm25_cache,
                )
            return shard.repository.search(query_embedding=query_embedding, top_k=top_k)
        except Exception as exc:  # shard isolation is a routing invariant
            logger.warning("subject shard %s failed; returning partial results: %s", shard.subject, exc)
            return []
