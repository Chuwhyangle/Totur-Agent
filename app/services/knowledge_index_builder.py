"""Build a deterministic knowledge index from a Markdown corpus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import Callable, Iterable, Protocol

from app.services.index_manifest import (
    CorpusFileManifest,
    IndexManifest,
    sha256_bytes,
)
from app.services.knowledge_chunker import KnowledgeChunk, chunk_markdown
from app.services.rag_settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_BATCH_SIZE,
    KNOWLEDGE_COLLECTION_NAME,
)


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class IndexRepository(Protocol):
    def rebuild(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> int: ...

    def upsert(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> int: ...

    def delete(self, ids: list[str]) -> int: ...

    def count(self) -> int: ...


@dataclass(frozen=True)
class IndexBuildResult:
    indexed_count: int
    manifest: IndexManifest
    updated_count: int = 0
    deleted_count: int = 0
    mode: str = "full"


def build_knowledge_index(
    *,
    corpus_root: Path,
    source_dir: Path | None = None,
    source_dirs: Iterable[Path] | None = None,
    source_files: Iterable[Path] | None = None,
    corpus_label: str,
    repository: IndexRepository,
    embedding_client: EmbeddingProvider,
    embedding_model: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    collection_name: str = KNOWLEDGE_COLLECTION_NAME,
    previous_manifest: IndexManifest | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> IndexBuildResult:
    """Build once, then update only files whose content hash changed."""

    _require_positive_batch_size(batch_size)
    _require_nonempty(corpus_label, "corpus_label")
    _require_nonempty(embedding_model, "embedding_model")
    _require_nonempty(collection_name, "collection_name")

    root = Path(corpus_root)
    source_paths = (
        _resolve_source_dirs(source_dir, source_dirs)
        if source_files is None
        else ()
    )
    if source_files is not None and (source_dir is not None or source_dirs is not None):
        raise ValueError("source_files cannot be combined with source_dir/source_dirs")
    if source_files is not None:
        normalized_files = tuple(Path(item) for item in source_files)
        if not normalized_files or any(path.is_absolute() for path in normalized_files):
            raise ValueError("source_files must contain relative paths")
        markdown_paths = sorted(
            {root / path for path in normalized_files if (root / path).is_file()},
            key=lambda path: path.relative_to(root).as_posix(),
        )
    else:
        markdown_paths = sorted(
            {
                path
                for source in source_paths
                for path in (root / source).rglob("*.md")
                if path.is_file()
            },
            key=lambda path: path.relative_to(root).as_posix(),
        )
    if not markdown_paths:
        raise ValueError(f"no markdown files found under {source_paths}")

    scanned = [
        (path.relative_to(root).as_posix(), raw, sha256_bytes(raw))
        for path in markdown_paths
        for raw in (path.read_bytes(),)
    ]
    incremental = _can_update_incrementally(
        previous_manifest,
        repository,
        collection_name=collection_name,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        corpus_label=corpus_label,
    )
    old_files = (
        {item.path: item for item in previous_manifest.files}
        if incremental and previous_manifest is not None
        else {}
    )

    changed_chunks: list[KnowledgeChunk] = []
    file_records: list[CorpusFileManifest] = []
    changed_sources: set[str] = set()
    for source, raw, content_hash in scanned:
        old = old_files.get(source)
        if old is not None and old.content_sha256 == content_hash:
            record = old
        else:
            file_chunks = chunk_markdown(
                raw.decode("utf-8"), source, chunk_size, chunk_overlap
            )
            changed_chunks.extend(file_chunks)
            changed_sources.add(source)
            record = CorpusFileManifest(source, content_hash, len(file_chunks))
        file_records.append(record)
        if progress is not None:
            progress(source, record.chunk_count)

    if sum(item.chunk_count for item in file_records) == 0:
        raise ValueError("corpus produced zero chunks")

    if incremental and previous_manifest is not None:
        removed_sources = set(old_files) - {item.path for item in file_records}
        if not changed_sources and not removed_sources:
            return IndexBuildResult(
                indexed_count=previous_manifest.chunk_count,
                manifest=previous_manifest,
                mode="unchanged",
            )
        expected_dimensions = previous_manifest.embedding_dimensions
    else:
        removed_sources = set()
        expected_dimensions = None

    embeddings, dimensions = _embed_chunks(
        changed_chunks,
        embedding_client,
        batch_size,
        expected_dimensions=expected_dimensions,
    )
    embedding_dimensions = dimensions or expected_dimensions
    if embedding_dimensions is None:
        raise ValueError("embedding vector dimensions are missing")

    manifest = IndexManifest.create(
        schema_version=1,
        collection_name=collection_name,
        built_at=datetime.now(timezone.utc).isoformat(),
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        corpus_root=corpus_label,
        files=file_records,
    )

    if not incremental:
        indexed_count = repository.rebuild(changed_chunks, embeddings)
        _require_repository_count(indexed_count, len(changed_chunks), "indexed")
        return IndexBuildResult(
            indexed_count=indexed_count,
            manifest=manifest,
            updated_count=indexed_count,
            deleted_count=(previous_manifest.chunk_count if previous_manifest else 0),
        )

    updated_count = 0
    if changed_chunks:
        updated_count = repository.upsert(changed_chunks, embeddings)
        _require_repository_count(updated_count, len(changed_chunks), "updated")

    delete_ids = _obsolete_chunk_ids(
        old_files, file_records, changed_sources, removed_sources
    )
    deleted_count = 0
    if delete_ids:
        deleted_count = repository.delete(delete_ids)
        _require_repository_count(deleted_count, len(delete_ids), "deleted")

    final_count = repository.count()
    _require_repository_count(final_count, manifest.chunk_count, "indexed")
    return IndexBuildResult(
        indexed_count=final_count,
        manifest=manifest,
        updated_count=updated_count,
        deleted_count=deleted_count,
        mode="incremental",
    )


def _embed_chunks(
    chunks: list[KnowledgeChunk],
    embedding_client: EmbeddingProvider,
    batch_size: int,
    *,
    expected_dimensions: int | None,
) -> tuple[list[list[float]], int | None]:
    embeddings: list[list[float]] = []
    dimensions = expected_dimensions
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        batch_embeddings = embedding_client.embed_texts(
            [chunk.content for chunk in batch]
        )
        try:
            returned_count = len(batch_embeddings)
        except TypeError as exc:
            raise ValueError("embedding result count is not measurable") from exc
        if returned_count != len(batch):
            raise ValueError("embedding result count does not match requested batch count")

        for offset, vector in enumerate(batch_embeddings):
            vector_index = start + offset
            try:
                vector_dimensions = len(vector)
            except TypeError as exc:
                raise ValueError("embedding vector dimension is not measurable") from exc
            if vector_dimensions <= 0:
                raise ValueError("embedding vector dimension must be positive")
            if dimensions is None:
                dimensions = vector_dimensions
            elif vector_dimensions != dimensions:
                raise ValueError("embedding vector dimensions do not match")
            for element_index, element in enumerate(vector):
                if (
                    isinstance(element, bool)
                    or not isinstance(element, Real)
                    or not isfinite(element)
                ):
                    raise ValueError(
                        f"embedding vector {vector_index} element {element_index} "
                        "must be a finite real number"
                    )
        embeddings.extend(batch_embeddings)
    return embeddings, dimensions


def _can_update_incrementally(
    manifest: IndexManifest | None,
    repository: IndexRepository,
    *,
    collection_name: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
    corpus_label: str,
) -> bool:
    if manifest is None or (
        manifest.schema_version != 1
        or manifest.collection_name != collection_name
        or manifest.embedding_model != embedding_model
        or manifest.chunk_size != chunk_size
        or manifest.chunk_overlap != chunk_overlap
        or manifest.corpus_root != corpus_label
    ):
        return False
    count = getattr(repository, "count", None)
    return callable(count) and count() == manifest.chunk_count


def _obsolete_chunk_ids(
    old_files: dict[str, CorpusFileManifest],
    new_files: list[CorpusFileManifest],
    changed_sources: set[str],
    removed_sources: set[str],
) -> list[str]:
    new_by_path = {item.path: item for item in new_files}
    ids = [
        f"{source}#{index}"
        for source in sorted(removed_sources)
        for index in range(old_files[source].chunk_count)
    ]
    for source in sorted(changed_sources & old_files.keys()):
        old_count = old_files[source].chunk_count
        new_count = new_by_path[source].chunk_count
        ids.extend(f"{source}#{index}" for index in range(new_count, old_count))
    return ids


def _require_repository_count(actual: int, expected: int, label: str) -> None:
    if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected:
        raise ValueError(f"repository {label} count does not match chunk count")


def _require_positive_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _require_nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _resolve_source_dirs(
    source_dir: Path | None, source_dirs: Iterable[Path] | None
) -> tuple[Path, ...]:
    if source_dir is not None and source_dirs is not None:
        raise ValueError("source_dir and source_dirs are mutually exclusive")
    if source_dirs is None:
        if source_dir is None:
            raise ValueError("at least one source directory is required")
        normalized = (Path(source_dir),)
    else:
        normalized = tuple(Path(item) for item in source_dirs)
        if not normalized:
            raise ValueError("at least one source directory is required")
    if any(path.is_absolute() for path in normalized):
        raise ValueError("source directories must be relative to corpus_root")
    return normalized
