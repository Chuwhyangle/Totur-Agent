"""Incrementally synchronize public JD parents and vectorized children."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol

from app.db.models import PUBLIC_JOB_DESCRIPTIONS_TABLE, PublicJDRecord
from app.repositories.jd_vector_repository import JD_COLLECTION_NAME
from app.services.jd_corpus import JDChildDocument, JDParentDocument
from app.services.jd_index_manifest import (
    JDChildManifest,
    JDIndexManifest,
    JDParentManifest,
    load_jd_manifest,
    write_jd_manifest,
)
from app.services.rag_settings import EMBEDDING_BATCH_SIZE


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class JDVectorStore(Protocol):
    def rebuild(self, children, embeddings) -> int: ...
    def upsert(self, children, embeddings) -> int: ...
    def delete(self, ids) -> int: ...
    def count(self) -> int: ...


SQLiteSync = Callable[..., int]
SQLiteCount = Callable[[], int]


@dataclass(frozen=True)
class JDIndexBuildResult:
    mode: str
    parent_count: int
    child_count: int
    updated_parent_count: int
    updated_child_count: int
    deleted_parent_count: int
    deleted_child_count: int
    manifest: JDIndexManifest | None = None


def build_jd_index(
    *,
    parents: Iterable[JDParentDocument],
    repository: JDVectorStore,
    embedding_client: EmbeddingProvider,
    embedding_model: str,
    manifest_path: Path,
    sync_sqlite: SQLiteSync,
    count_sqlite: SQLiteCount,
    collection_name: str = JD_COLLECTION_NAME,
    sqlite_table: str = PUBLIC_JOB_DESCRIPTIONS_TABLE,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    full: bool = False,
    dry_run: bool = False,
) -> JDIndexBuildResult:
    """Apply one fail-closed JD snapshot build with child-level embedding diffs."""

    normalized_parents = tuple(sorted(parents, key=lambda item: item.jd_id))
    if not normalized_parents:
        raise ValueError("JD index requires at least one parent")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not embedding_model.strip():
        raise ValueError("embedding_model must be non-empty")

    previous = _load_previous_manifest(Path(manifest_path), full=full)
    incremental = _can_update_incrementally(
        previous,
        repository=repository,
        count_sqlite=count_sqlite,
        collection_name=collection_name,
        sqlite_table=sqlite_table,
        embedding_model=embedding_model,
    )
    old_parents = (
        {parent.jd_id: parent for parent in previous.parents}
        if incremental and previous is not None
        else {}
    )
    new_by_id = {parent.jd_id: parent for parent in normalized_parents}
    changed_children = [
        child
        for parent in normalized_parents
        for child in parent.children
        if _child_changed(old_parents.get(parent.jd_id), child)
    ]
    updated_parents = [
        parent
        for parent in normalized_parents
        if _parent_record_changed(old_parents.get(parent.jd_id), parent)
    ]
    removed_parent_ids = sorted(set(old_parents) - set(new_by_id))
    removed_child_ids = [
        child.child_id
        for jd_id in removed_parent_ids
        for child in old_parents[jd_id].children
    ]

    if incremental and not (
        changed_children or updated_parents or removed_parent_ids
    ):
        return JDIndexBuildResult(
            mode="unchanged",
            parent_count=len(normalized_parents),
            child_count=sum(len(parent.children) for parent in normalized_parents),
            updated_parent_count=0,
            updated_child_count=0,
            deleted_parent_count=0,
            deleted_child_count=0,
            manifest=previous,
        )

    mode = "incremental" if incremental else "full"
    if dry_run:
        return JDIndexBuildResult(
            mode=f"dry-run-{mode}",
            parent_count=len(normalized_parents),
            child_count=sum(len(parent.children) for parent in normalized_parents),
            updated_parent_count=len(updated_parents),
            updated_child_count=len(changed_children),
            deleted_parent_count=len(removed_parent_ids),
            deleted_child_count=len(removed_child_ids),
        )

    expected_dimensions = previous.embedding_dimensions if incremental and previous else None
    embeddings, dimensions = _embed_children(
        changed_children,
        embedding_client,
        batch_size=batch_size,
        expected_dimensions=expected_dimensions,
    )
    embedding_dimensions = dimensions or expected_dimensions
    if embedding_dimensions is None:
        raise ValueError("JD embedding dimensions are missing")

    manifest = _create_manifest(
        parents=normalized_parents,
        collection_name=collection_name,
        sqlite_table=sqlite_table,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
    path = Path(manifest_path)
    path.unlink(missing_ok=True)

    records = [_record_from_parent(parent) for parent in updated_parents]
    if incremental:
        sqlite_count = sync_sqlite(records, removed_parent_ids)
        if changed_children:
            updated_count = repository.upsert(changed_children, embeddings)
            _require_count(updated_count, len(changed_children), "updated children")
        if removed_child_ids:
            deleted_count = repository.delete(removed_child_ids)
            _require_count(deleted_count, len(removed_child_ids), "deleted children")
    else:
        all_children = [child for parent in normalized_parents for child in parent.children]
        sqlite_count = sync_sqlite(
            [_record_from_parent(parent) for parent in normalized_parents],
            [],
            full_rebuild=True,
        )
        indexed_count = repository.rebuild(all_children, embeddings)
        _require_count(indexed_count, len(all_children), "indexed children")

    _require_count(sqlite_count, manifest.parent_count, "SQLite parents")
    _require_count(repository.count(), manifest.child_count, "Chroma children")
    _require_count(count_sqlite(), manifest.parent_count, "SQLite verified parents")
    write_jd_manifest(path, manifest)
    return JDIndexBuildResult(
        mode=mode,
        parent_count=manifest.parent_count,
        child_count=manifest.child_count,
        updated_parent_count=len(updated_parents),
        updated_child_count=len(changed_children),
        deleted_parent_count=len(removed_parent_ids),
        deleted_child_count=len(removed_child_ids),
        manifest=manifest,
    )


def _load_previous_manifest(path: Path, *, full: bool) -> JDIndexManifest | None:
    if full or not path.exists():
        return None
    try:
        return load_jd_manifest(path)
    except ValueError:
        return None


def _can_update_incrementally(
    manifest: JDIndexManifest | None,
    *,
    repository: JDVectorStore,
    count_sqlite: SQLiteCount,
    collection_name: str,
    sqlite_table: str,
    embedding_model: str,
) -> bool:
    return bool(
        manifest is not None
        and manifest.collection_name == collection_name
        and manifest.sqlite_table == sqlite_table
        and manifest.embedding_model == embedding_model
        and repository.count() == manifest.child_count
        and count_sqlite() == manifest.parent_count
    )


def _child_changed(
    old_parent: JDParentManifest | None,
    child: JDChildDocument,
) -> bool:
    if old_parent is None:
        return True
    old_children = {item.child_id: item for item in old_parent.children}
    old_child = old_children.get(child.child_id)
    return old_child is None or old_child.index_sha256 != child.index_sha256


def _parent_record_changed(
    old_parent: JDParentManifest | None,
    parent: JDParentDocument,
) -> bool:
    return bool(
        old_parent is None
        or old_parent.parent_sha256 != parent.parent_sha256
        or old_parent.row_sha256 != parent.row_sha256
    )


def _embed_children(
    children: list[JDChildDocument],
    embedding_client: EmbeddingProvider,
    *,
    batch_size: int,
    expected_dimensions: int | None,
) -> tuple[list[list[float]], int | None]:
    embeddings: list[list[float]] = []
    dimensions = expected_dimensions
    for start in range(0, len(children), batch_size):
        batch = children[start : start + batch_size]
        vectors = embedding_client.embed_texts([child.content for child in batch])
        if len(vectors) != len(batch):
            raise ValueError("JD embedding result count does not match")
        for vector in vectors:
            if not vector:
                raise ValueError("JD embedding vector must not be empty")
            if dimensions is None:
                dimensions = len(vector)
            elif len(vector) != dimensions:
                raise ValueError("JD embedding vector dimensions do not match")
        embeddings.extend(vectors)
    return embeddings, dimensions


def _create_manifest(
    *,
    parents: tuple[JDParentDocument, ...],
    collection_name: str,
    sqlite_table: str,
    embedding_model: str,
    embedding_dimensions: int,
) -> JDIndexManifest:
    manifest_parents = [
        JDParentManifest(
            jd_id=parent.jd_id,
            fingerprint=parent.fingerprint,
            category=parent.category,
            source_path=parent.source_path,
            parent_sha256=parent.parent_sha256,
            row_sha256=parent.row_sha256,
            children=tuple(
                sorted(
                    JDChildManifest(
                        child_id=child.child_id,
                        child_type=child.child_type,
                        index_sha256=child.index_sha256,
                    )
                    for child in parent.children
                )
            ),
        )
        for parent in parents
    ]
    return JDIndexManifest.create(
        collection_name=collection_name,
        sqlite_table=sqlite_table,
        built_at=datetime.now(timezone.utc).isoformat(),
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        parents=manifest_parents,
    )


def _record_from_parent(parent: JDParentDocument) -> PublicJDRecord:
    return PublicJDRecord(
        jd_id=parent.jd_id,
        fingerprint=parent.fingerprint,
        category=parent.category,
        source_path=parent.source_path,
        source_url=parent.source_url,
        title=parent.title,
        company=parent.company,
        salary_raw=parent.salary_raw,
        salary_min_k=parent.salary_min_k,
        salary_max_k=parent.salary_max_k,
        education=parent.education,
        recruitment_count=parent.recruitment_count,
        major=parent.major,
        region=parent.region,
        province=parent.province,
        source_updated_at=parent.source_updated_at,
        industry=parent.industry,
        company_type=parent.company_type,
        company_size=parent.company_size,
        relevance=parent.relevance,
        relevance_score=parent.relevance_score,
        function_category=parent.function_category,
        keywords=parent.keywords,
        duplicate_count=parent.duplicate_count,
        row_sha256=parent.row_sha256,
        parent_sha256=parent.parent_sha256,
    )


def _require_count(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise ValueError(f"JD {label} count does not match: {actual} != {expected}")
