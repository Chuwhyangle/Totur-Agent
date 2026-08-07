"""Build or incrementally synchronize the public JD parent-child index."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.embedding_client import EmbeddingClient
from app.config import load_embedding_config
from app.repositories.jd_vector_repository import JDVectorRepository
from app.repositories.public_jd_repository import count_public_jds, sync_public_jds
from app.services.jd_corpus import load_jd_dataset
from app.services.jd_index_builder import build_jd_index
from app.services.rag_settings import CHROMA_PERSIST_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize corpus/JD into SQLite and Chroma."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the diff without embedding or writing either store.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore the previous manifest and rebuild the complete snapshot.",
    )
    args = parser.parse_args(argv)

    try:
        parents = load_jd_dataset(PROJECT_ROOT)
        config = load_embedding_config()
        result = build_jd_index(
            parents=parents,
            repository=JDVectorRepository(),
            embedding_client=EmbeddingClient(config),
            embedding_model=config.model,
            manifest_path=(
                PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest_jd.json"
            ),
            sync_sqlite=sync_public_jds,
            count_sqlite=count_public_jds,
            full=args.full,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"JD 索引同步失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"mode={result.mode} parents={result.parent_count} children={result.child_count} "
        f"updated_parents={result.updated_parent_count} "
        f"updated_children={result.updated_child_count} "
        f"deleted_parents={result.deleted_parent_count} "
        f"deleted_children={result.deleted_child_count}"
    )
    if result.manifest is not None:
        print(f"fingerprint={result.manifest.fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
