"""Build the persistent Chroma knowledge index and its Manifest."""

from __future__ import annotations

from pathlib import Path
import sys

from chromadb.errors import ChromaError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.index_manifest import ManifestError, load_manifest, write_manifest
from app.services.knowledge_index_builder import build_knowledge_index
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    KNOWLEDGE_SOURCE_DIRS,
)


class _ManifestTrackingRepository:
    """Remove stale metadata immediately before the first index mutation."""

    def __init__(self, repository, manifest_path: Path) -> None:
        self.repository = repository
        self.manifest_path = manifest_path
        self.rebuild_attempted = False
        self.mutation_attempted = False

    def _before_mutation(self) -> None:
        if not self.mutation_attempted:
            self.manifest_path.unlink(missing_ok=True)
            self.mutation_attempted = True

    def rebuild(self, chunks, embeddings) -> int:
        self._before_mutation()
        self.rebuild_attempted = True
        return self.repository.rebuild(chunks, embeddings)

    def upsert(self, chunks, embeddings) -> int:
        self._before_mutation()
        return self.repository.upsert(chunks, embeddings)

    def delete(self, ids) -> int:
        self._before_mutation()
        return self.repository.delete(ids)

    def count(self) -> int:
        return self.repository.count()


def main() -> int:
    """Rebuild the live index, then atomically persist its validated Manifest."""

    manifest_path = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"
    try:
        config = load_embedding_config()
        try:
            previous_manifest = (
                load_manifest(manifest_path) if manifest_path.exists() else None
            )
        except ManifestError:
            previous_manifest = None
        repository = _ManifestTrackingRepository(
            KnowledgeRepository(),
            manifest_path,
        )
        result = build_knowledge_index(
            corpus_root=PROJECT_ROOT,
            source_dirs=tuple(Path(item) for item in KNOWLEDGE_SOURCE_DIRS),
            corpus_label="+".join(KNOWLEDGE_SOURCE_DIRS),
            repository=repository,
            embedding_client=EmbeddingClient(config=config),
            embedding_model=config.model,
            previous_manifest=previous_manifest,
            progress=lambda source, count: print(f"{source}: {count} chunks"),
        )
        write_manifest(manifest_path, result.manifest)
    except (
        ChromaError,
        RuntimeError,
        EmbeddingError,
        ManifestError,
        ValueError,
        OSError,
    ) as exc:
        print(f"构建学习笔记索引失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"索引构建完成：files={result.manifest.file_count} "
        f"chunks={result.indexed_count} "
        f"mode={result.mode} updated={result.updated_count} "
        f"deleted={result.deleted_count} "
        f"collection={result.manifest.collection_name} "
        f"fingerprint={result.manifest.fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
