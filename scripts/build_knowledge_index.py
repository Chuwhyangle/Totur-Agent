"""Build the persistent Chroma knowledge index and its manifests."""

from __future__ import annotations

from collections import defaultdict
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
    COLLECTION_PREFIX,
    ENABLE_SUBJECT_SHARDING,
    EXTERNAL_CORPUS_SUBJECT,
    KNOWLEDGE_SOURCE_DIRS,
    collection_name_for_subject,
    subject_slug,
)


class _ManifestTrackingRepository:
    """Remove stale metadata immediately before the first index mutation."""

    def __init__(self, repository, manifest_path: Path) -> None:
        self.repository = repository
        self.manifest_path = manifest_path
        self.rebuild_attempted = False
        self.mutation_attempted = False

    @property
    def collection_name(self):
        return self.repository.collection_name

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


def _subject_inputs(root: Path) -> dict[str, tuple[tuple[Path, ...], tuple[Path, ...]]]:
    """Discover first-level docs subjects plus the fixed external llm subject."""

    directories: dict[str, list[Path]] = defaultdict(list)
    files: dict[str, list[Path]] = defaultdict(list)
    docs_root = root / "docs"
    if docs_root.is_dir():
        for path in sorted(docs_root.glob("*.md")):
            files["general"].append(path.relative_to(root))
        for child in sorted(docs_root.iterdir()):
            if not child.is_dir():
                continue
            if not any(item.is_file() for item in child.rglob("*.md")):
                print(f"warning: skipping empty subject directory {child}", file=sys.stderr)
                continue
            slug = subject_slug(child.name)
            directories[slug].append(child.relative_to(root))

    external_root = root / "corpus" / "self-llm" / "docs"
    if external_root.is_dir() and any(item.is_file() for item in external_root.rglob("*.md")):
        directories[EXTERNAL_CORPUS_SUBJECT].append(external_root.relative_to(root))
    elif external_root.exists():
        print(f"warning: skipping empty external corpus {external_root}", file=sys.stderr)

    return {
        subject: (tuple(directories.get(subject, [])), tuple(files.get(subject, [])))
        for subject in sorted(set(directories) | set(files))
    }


def _build_one(
    *,
    root: Path,
    subject: str,
    source_dirs: tuple[Path, ...],
    source_files: tuple[Path, ...],
    config,
    embedding_client,
    client,
) -> object:
    collection_name = collection_name_for_subject(subject)
    manifest_path = root / CHROMA_PERSIST_DIR / f"index_manifest_{subject}.json"
    try:
        previous_manifest = load_manifest(manifest_path) if manifest_path.exists() else None
    except ManifestError:
        previous_manifest = None
    repository = _ManifestTrackingRepository(
        KnowledgeRepository(client=client, collection_name=collection_name),
        manifest_path,
    )
    kwargs = {
        "corpus_root": root,
        "corpus_label": subject,
        "repository": repository,
        "embedding_client": embedding_client,
        "embedding_model": config.model,
        "collection_name": collection_name,
        "previous_manifest": previous_manifest,
        "progress": lambda source, count: print(f"[{subject}] {source}: {count} chunks"),
    }
    if source_files:
        kwargs["source_files"] = source_files
    else:
        kwargs["source_dirs"] = source_dirs
    result = build_knowledge_index(**kwargs)
    write_manifest(manifest_path, result.manifest)
    return result


def main() -> int:
    """Build one legacy index or independent per-subject shard indexes."""

    try:
        config = load_embedding_config()
        embedding_client = EmbeddingClient(config=config)
        if not ENABLE_SUBJECT_SHARDING:
            manifest_path = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"
            try:
                previous_manifest = load_manifest(manifest_path) if manifest_path.exists() else None
            except ManifestError:
                previous_manifest = None
            repository = _ManifestTrackingRepository(KnowledgeRepository(), manifest_path)
            result = build_knowledge_index(
                corpus_root=PROJECT_ROOT,
                source_dirs=tuple(Path(item) for item in KNOWLEDGE_SOURCE_DIRS),
                corpus_label="+".join(KNOWLEDGE_SOURCE_DIRS),
                repository=repository,
                embedding_client=embedding_client,
                embedding_model=config.model,
                previous_manifest=previous_manifest,
                progress=lambda source, count: print(f"{source}: {count} chunks"),
            )
            write_manifest(manifest_path, result.manifest)
            results = [result]
        else:
            import chromadb

            client = chromadb.PersistentClient(path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR))
            inputs = _subject_inputs(PROJECT_ROOT)
            if not inputs:
                print(
                    f"warning: no subject corpus found; falling back to legacy {COLLECTION_PREFIX.rstrip('_')} index",
                    file=sys.stderr,
                )
                manifest_path = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"
                previous_manifest = load_manifest(manifest_path) if manifest_path.exists() else None
                repository = _ManifestTrackingRepository(KnowledgeRepository(client=client), manifest_path)
                result = build_knowledge_index(
                    corpus_root=PROJECT_ROOT,
                    source_dirs=tuple(Path(item) for item in KNOWLEDGE_SOURCE_DIRS),
                    corpus_label="+".join(KNOWLEDGE_SOURCE_DIRS),
                    repository=repository,
                    embedding_client=embedding_client,
                    embedding_model=config.model,
                    previous_manifest=previous_manifest,
                )
                write_manifest(manifest_path, result.manifest)
                results = [result]
            else:
                results = [
                    _build_one(
                        root=PROJECT_ROOT, subject=subject, source_dirs=dirs, source_files=files,
                        config=config, embedding_client=embedding_client, client=client,
                    )
                    for subject, (dirs, files) in inputs.items()
                ]
    except (ChromaError, RuntimeError, EmbeddingError, ManifestError, ValueError, OSError) as exc:
        print(f"构建学习笔记索引失败：{exc}", file=sys.stderr)
        return 1

    for result in results:
        print(
        f"索引构建完成：files={result.manifest.file_count} "
            f"chunks={result.indexed_count} "
            f"mode={result.mode} updated={result.updated_count} deleted={result.deleted_count} "
            f"collection={result.manifest.collection_name} fingerprint={result.manifest.fingerprint}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
