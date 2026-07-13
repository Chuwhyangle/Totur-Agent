"""Build the persistent Chroma knowledge index and its Manifest."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.index_manifest import ManifestError, write_manifest
from app.services.knowledge_index_builder import build_knowledge_index
from app.services.rag_settings import CHROMA_PERSIST_DIR, KNOWLEDGE_SOURCE_DIR


def main() -> int:
    """Rebuild the live index, then atomically persist its validated Manifest."""

    try:
        config = load_embedding_config()
        result = build_knowledge_index(
            corpus_root=PROJECT_ROOT,
            source_dir=Path(KNOWLEDGE_SOURCE_DIR),
            corpus_label=KNOWLEDGE_SOURCE_DIR,
            repository=KnowledgeRepository(),
            embedding_client=EmbeddingClient(config=config),
            embedding_model=config.model,
            progress=lambda source, count: print(f"{source}: {count} chunks"),
        )
        write_manifest(
            PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json",
            result.manifest,
        )
    except (
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
        f"collection={result.manifest.collection_name} "
        f"fingerprint={result.manifest.fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
