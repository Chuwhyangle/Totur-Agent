"""Build the local Chroma knowledge index from Markdown notes."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge_chunker import KnowledgeChunk, chunk_markdown
from app.services.rag_settings import (
    EMBEDDING_BATCH_SIZE,
    KNOWLEDGE_COLLECTION_NAME,
    KNOWLEDGE_SOURCE_DIR,
)


def main() -> int:
    """扫描 docs Markdown，生成 embedding，并全量重建 Chroma 集合。"""

    try:
        embedding_client = EmbeddingClient(config=load_embedding_config())
        chunks = _load_chunks()
        embeddings = _embed_chunks(embedding_client, chunks)
        count = KnowledgeRepository().rebuild(chunks, embeddings)
    except (RuntimeError, EmbeddingError, ValueError) as exc:
        print(f"构建学习笔记索引失败：{exc}", file=sys.stderr)
        return 1

    source_count = len({chunk.source for chunk in chunks})
    print(
        f"索引构建完成：files={source_count} chunks={count} "
        f"collection={KNOWLEDGE_COLLECTION_NAME}"
    )
    return 0


def _load_chunks() -> list[KnowledgeChunk]:
    """读取 docs/**/*.md，并按文件名排序保证重建顺序确定。"""

    source_root = PROJECT_ROOT / KNOWLEDGE_SOURCE_DIR
    markdown_files = sorted(source_root.rglob("*.md"))
    chunks: list[KnowledgeChunk] = []

    for path in markdown_files:
        source = path.relative_to(PROJECT_ROOT).as_posix()
        file_chunks = chunk_markdown(
            text=path.read_text(encoding="utf-8"),
            source=source,
        )
        chunks.extend(file_chunks)
        print(f"{source}: {len(file_chunks)} chunks")

    return chunks


def _embed_chunks(
    embedding_client: EmbeddingClient,
    chunks: list[KnowledgeChunk],
) -> list[list[float]]:
    """按批次调用 embedding API，避免单次请求过大。"""

    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        embeddings.extend(
            embedding_client.embed_texts([chunk.content for chunk in batch])
        )

    return embeddings


if __name__ == "__main__":
    raise SystemExit(main())

