"""Search the committed public JD corpus through the shared RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.models import PUBLIC_JOB_DESCRIPTIONS_TABLE, PublicJDRecord
from app.repositories.jd_vector_repository import JDVectorRepository
from app.repositories.knowledge_repository import KnowledgeHit
from app.repositories.public_jd_repository import list_public_jds
from app.services.hybrid_retriever import hybrid_search
from app.services.jd_index_manifest import JDIndexManifest, JDParentManifest
from app.services.jd_index_state import JDIndexNotReadyError, load_ready_jd_manifest
from app.services.reranking import RerankingService
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    ENABLE_RERANKING,
    ENABLE_HYBRID_RETRIEVAL,
    RERANK_CANDIDATE_K,
    SIMILARITY_THRESHOLD,
)


DEFAULT_LIMIT = 3
MAX_LIMIT = 5
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest_jd.json"

_repository: JDVectorRepository | None = None
_embedding_client: EmbeddingClient | None = None
_reranking_service: RerankingService | None = None


@dataclass(frozen=True)
class _ParentCandidate:
    parent: JDParentManifest
    record: PublicJDRecord
    hit: KnowledgeHit
    categories: tuple[str, ...]


class _FilteredRepository:
    """Bind one Chroma where-clause to the existing hybrid protocol."""

    def __init__(self, repository: JDVectorRepository, where: dict[str, Any] | None):
        self.repository = repository
        self.where = where
        signature = json.dumps(where or {}, sort_keys=True, ensure_ascii=False)
        self.collection_name = f"{repository.collection_name}:{signature}"

    def search(self, query_embedding, top_k):
        return self.repository.search(query_embedding, top_k, where=self.where)

    def list_entries(self, include_embeddings=False):
        return self.repository.list_entries(
            include_embeddings=include_embeddings,
            where=self.where,
        )


def search_job_descriptions(
    query: str,
    limit: int | None = None,
    direction: str | None = None,
    relevance: str | None = None,
    education: str | None = None,
    province: str | None = None,
    salary_floor_k: float | None = None,
    salary_ceiling_k: float | None = None,
) -> dict[str, Any]:
    """Return complete parent JDs after child retrieval and parent deduplication."""

    if not isinstance(query, str) or not query.strip():
        return _error("invalid_arguments", "query must be a non-empty string")
    try:
        safe_limit = _clamp_limit(limit)
        safe_floor, safe_ceiling = _validate_salary_filters(
            salary_floor_k, salary_ceiling_k
        )
    except (TypeError, ValueError) as exc:
        return _error("invalid_arguments", str(exc))

    repository = _get_repository()
    records = list_public_jds()
    try:
        manifest = load_ready_jd_manifest(
            MANIFEST_PATH,
            collection_name=repository.collection_name,
            vector_count=repository.count(),
            vector_snapshot=repository.snapshot_hashes(),
            sqlite_table=PUBLIC_JOB_DESCRIPTIONS_TABLE,
            sqlite_count=len(records),
            sqlite_snapshot={
                record.jd_id: (record.row_sha256, record.parent_sha256)
                for record in records
            },
        )
    except JDIndexNotReadyError as exc:
        return _error("jd_index_not_ready", f"JD index is not ready: {exc}")

    embedding_client = _get_embedding_client()
    if embedding_client.config.model != manifest.embedding_model:
        return _error(
            "jd_index_not_ready",
            "JD index is not ready: embedding model does not match manifest",
        )

    stripped_query = query.strip()
    try:
        query_embedding = embedding_client.embed_texts([stripped_query])[0]
    except (EmbeddingError, IndexError) as exc:
        return _error("embedding_failed", f"embedding failed: {exc}")
    if len(query_embedding) != manifest.embedding_dimensions:
        return _error(
            "embedding_failed",
            "query embedding dimensions do not match the JD index",
        )

    where = _build_where(
        direction=direction,
        relevance=relevance,
        education=education,
        province=province,
        salary_floor_k=safe_floor,
        salary_ceiling_k=safe_ceiling,
    )
    child_candidate_k = max(safe_limit * 4, RERANK_CANDIDATE_K)
    if ENABLE_HYBRID_RETRIEVAL:
        filtered_repository = _FilteredRepository(repository, where)
        hits = hybrid_search(
            repository=filtered_repository,
            query=stripped_query,
            query_embedding=query_embedding,
            top_k=child_candidate_k,
            fingerprint=manifest.fingerprint,
        )
    else:
        hits = repository.search(
            query_embedding,
            child_candidate_k,
            where=where,
        )
    hits = [hit for hit in hits if hit.similarity >= SIMILARITY_THRESHOLD]
    candidates = _parent_candidates(hits, manifest, records)
    ranked, rerank_summary = _rank_candidates(candidates, stripped_query, safe_limit)

    items: list[dict[str, Any]] = []
    for candidate in ranked:
        try:
            content = _read_parent(candidate.parent)
        except (OSError, UnicodeError, ValueError) as exc:
            return _error("jd_index_stale", f"JD parent snapshot is stale: {exc}")
        item = {
            "jd_id": candidate.record.jd_id,
            "fingerprint": candidate.record.fingerprint,
            "categories": list(candidate.categories),
            "title": candidate.record.title,
            "company": candidate.record.company,
            "source": candidate.record.source_path,
            "source_url": candidate.record.source_url,
            "matched_child_type": candidate.hit.title_path,
            "similarity": round(candidate.hit.similarity, 4),
            "match_score": round(candidate.hit.similarity * 100),
            "content": content,
        }
        rerank_score = rerank_summary["scores"].get(candidate.record.source_path)
        if rerank_score is not None:
            item["rerank_score"] = round(rerank_score, 6)
        items.append(item)

    result: dict[str, Any] = {
        "ok": True,
        "found": bool(items),
        "query": query,
        "count": len(items),
        "results": items,
        "items": items,
        "summary": {
            "returned_count": len(items),
            "candidate_parent_count": len(candidates),
            "rerank_applied": rerank_summary["applied"],
            "rerank_fallback_reason": rerank_summary["fallback_reason"],
        },
    }
    if not items:
        result["message"] = "未找到相关 JD。"
    return result


def _parent_candidates(
    hits: list[KnowledgeHit],
    manifest: JDIndexManifest,
    records: list[PublicJDRecord],
) -> list[_ParentCandidate]:
    parent_by_source = {parent.source_path: parent for parent in manifest.parents}
    record_by_source = {record.source_path: record for record in records}
    categories_by_fingerprint: dict[str, set[str]] = {}
    for record in records:
        categories_by_fingerprint.setdefault(record.fingerprint, set()).add(record.category)
    best_by_source: dict[str, KnowledgeHit] = {}
    for hit in hits:
        current = best_by_source.get(hit.source)
        if current is None or hit.similarity > current.similarity:
            best_by_source[hit.source] = hit
    best_by_fingerprint: dict[str, _ParentCandidate] = {}
    for source, hit in best_by_source.items():
        parent = parent_by_source.get(source)
        record = record_by_source.get(source)
        if parent is None or record is None:
            continue
        candidate = _ParentCandidate(
            parent=parent,
            record=record,
            hit=hit,
            categories=tuple(sorted(categories_by_fingerprint[record.fingerprint])),
        )
        current = best_by_fingerprint.get(record.fingerprint)
        if current is None or (-hit.similarity, source) < (
            -current.hit.similarity,
            current.record.source_path,
        ):
            best_by_fingerprint[record.fingerprint] = candidate
    return sorted(
        best_by_fingerprint.values(),
        key=lambda item: (-item.hit.similarity, item.record.source_path),
    )


def _rank_candidates(
    candidates: list[_ParentCandidate], query: str, limit: int
) -> tuple[list[_ParentCandidate], dict[str, Any]]:
    if not ENABLE_RERANKING or not candidates:
        return candidates[:limit], {
            "applied": False,
            "fallback_reason": None,
            "scores": {},
        }
    hits = [candidate.hit for candidate in candidates]
    outcome = _get_reranking_service().rerank(query, hits, top_n=limit)
    candidate_by_source = {candidate.record.source_path: candidate for candidate in candidates}
    ranked = [
        candidate_by_source[hit.source]
        for hit in outcome.hits
        if hit.source in candidate_by_source
    ]
    scores = {
        hits[index].source: score
        for index, score in outcome.scores_by_index.items()
        if index < len(hits)
    }
    return ranked, {
        "applied": outcome.applied,
        "fallback_reason": outcome.fallback_reason,
        "scores": scores if outcome.applied else {},
    }


def _read_parent(parent: JDParentManifest) -> str:
    path = PROJECT_ROOT / parent.source_path
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != parent.parent_sha256:
        raise ValueError(f"hash mismatch for {parent.source_path}")
    return raw.decode("utf-8")


def _build_where(
    *,
    direction: str | None,
    relevance: str | None,
    education: str | None,
    province: str | None,
    salary_floor_k: float | None,
    salary_ceiling_k: float | None,
) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    for field, value in (
        ("category", direction),
        ("relevance", relevance),
        ("education", education),
        ("province", province),
    ):
        if value is not None and str(value).strip():
            conditions.append({field: str(value).strip()})
    if salary_floor_k is not None:
        conditions.append({"salary_min_k": {"$gte": salary_floor_k}})
    if salary_ceiling_k is not None:
        conditions.append({"salary_max_k": {"$lte": salary_ceiling_k}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _validate_salary_filters(
    floor: float | None, ceiling: float | None
) -> tuple[float | None, float | None]:
    safe_floor = float(floor) if floor is not None else None
    safe_ceiling = float(ceiling) if ceiling is not None else None
    if safe_floor is not None and safe_floor < 0:
        raise ValueError("salary_floor_k must be non-negative")
    if safe_ceiling is not None and safe_ceiling < 0:
        raise ValueError("salary_ceiling_k must be non-negative")
    if safe_floor is not None and safe_ceiling is not None and safe_floor > safe_ceiling:
        raise ValueError("salary_floor_k must not exceed salary_ceiling_k")
    return safe_floor, safe_ceiling


def _clamp_limit(limit: int | None) -> int:
    parsed = DEFAULT_LIMIT if limit is None else int(limit)
    return max(1, min(parsed, MAX_LIMIT))


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message}


def _get_repository() -> JDVectorRepository:
    global _repository
    if _repository is None:
        _repository = JDVectorRepository()
    return _repository


def _get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def _get_reranking_service() -> RerankingService:
    global _reranking_service
    if _reranking_service is None:
        _reranking_service = RerankingService(enabled=True)
    return _reranking_service
