"""Build a deterministic, shared knowledge index from a Markdown corpus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import Callable, Protocol

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
    """Provider capable of embedding a batch of chunk texts."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector for every input text."""
        ...


class IndexRepository(Protocol):
    """Repository that replaces the current index with a complete rebuild."""

    def rebuild(
        self,
        chunks: list[KnowledgeChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Rebuild the index and return the number of indexed chunks."""
        ...


@dataclass(frozen=True)
class IndexBuildResult:
    """The validated manifest and count produced by one index build."""

    indexed_count: int
    manifest: IndexManifest


def build_knowledge_index(
    *,
    corpus_root: Path,
    source_dir: Path,
    corpus_label: str,
    repository: IndexRepository,
    embedding_client: EmbeddingProvider,
    embedding_model: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    collection_name: str = KNOWLEDGE_COLLECTION_NAME,
    progress: Callable[[str, int], None] | None = None,
) -> IndexBuildResult:
    """Read, chunk, embed, and atomically hand a complete corpus to a repository."""

    _require_positive_batch_size(batch_size)
    _require_nonempty(corpus_label, "corpus_label")
    _require_nonempty(embedding_model, "embedding_model")
    _require_nonempty(collection_name, "collection_name")

    root = Path(corpus_root)
    source_root = root / source_dir
    markdown_paths = sorted(
        (
            path
            for path in source_root.rglob("*.md")
            if path.is_file()
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not markdown_paths:
        raise ValueError(f"no markdown files found under {source_root}")

    chunks: list[KnowledgeChunk] = []
    file_records: list[CorpusFileManifest] = []
    for path in markdown_paths:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8")
        source = path.relative_to(root).as_posix()
        file_chunks = chunk_markdown(
            text,
            source,
            chunk_size,
            chunk_overlap,
        )
        chunks.extend(file_chunks)
        file_records.append(
            CorpusFileManifest(
                path=source,
                content_sha256=sha256_bytes(raw_bytes),
                chunk_count=len(file_chunks),
            )
        )
        if progress is not None:
            progress(source, len(file_chunks))

    if not chunks:
        raise ValueError("corpus produced zero chunks")

    embeddings: list[list[float]] = []
    embedding_dimensions: int | None = None
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
            raise ValueError(
                "embedding result count does not match requested batch count"
            )

        for batch_vector_index, vector in enumerate(batch_embeddings):
            vector_index = start + batch_vector_index
            try:
                dimensions = len(vector)
            except TypeError as exc:
                raise ValueError("embedding vector dimension is not measurable") from exc
            if dimensions <= 0:
                raise ValueError("embedding vector dimension must be positive")
            if embedding_dimensions is None:
                embedding_dimensions = dimensions
            elif dimensions != embedding_dimensions:
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

    indexed_count = repository.rebuild(chunks, embeddings)
    if (
        isinstance(indexed_count, bool)
        or not isinstance(indexed_count, int)
        or indexed_count != len(chunks)
    ):
        raise ValueError(
            "repository indexed count does not match chunk count"
        )

    return IndexBuildResult(indexed_count=indexed_count, manifest=manifest)


def _require_positive_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _require_nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
