"""Inspect the persisted knowledge-index Manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.index_manifest import ManifestError, load_manifest
from app.services.rag_settings import CHROMA_PERSIST_DIR

DEFAULT_MANIFEST_PATH = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"


def main(argv: list[str] | None = None) -> int:
    """Load, validate, and print the persisted index Manifest."""

    parser = argparse.ArgumentParser(description="Inspect knowledge index Manifest.")
    parser.add_argument("--path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.path)
    except ManifestError as exc:
        print(f"读取索引 Manifest 失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"fingerprint: {manifest.fingerprint}")
    print(f"collection: {manifest.collection_name}")
    print(f"embedding_model: {manifest.embedding_model}")
    print(f"embedding_dimensions: {manifest.embedding_dimensions}")
    print(f"chunk_size: {manifest.chunk_size}")
    print(f"chunk_overlap: {manifest.chunk_overlap}")
    print(f"files: {manifest.file_count}")
    print(f"chunks: {manifest.chunk_count}")
    print(f"built_at: {manifest.built_at}")
    if args.files:
        for item in manifest.files:
            print(
                f"- {item.path} chunks={item.chunk_count} "
                f"sha256={item.content_sha256}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
