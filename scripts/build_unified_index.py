"""Build the unified `knowledge` Chroma collection from existing indexes.

方案 A（统一单集合）：把 learning_notes 与 job_descriptions 两个现有集合
合并进同一个 `knowledge` 集合，metadata 统一加 `doc_type` 区分类型。
向量直接拷贝（两集合同模型、同维度、同 cosine 空间），不重新 embedding。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.services.rag_settings import CHROMA_PERSIST_DIR


UNIFIED_COLLECTION_NAME = "knowledge"
NOTE_COLLECTION_NAME = "learning_notes"
JD_COLLECTION_NAME = "job_descriptions"
BATCH_SIZE = 512


def _read_collection(client, name: str) -> dict:
    """Read all entries (ids, documents, metadatas, embeddings) from a collection."""

    collection = client.get_collection(name)
    result = collection.get(include=["documents", "metadatas", "embeddings"])
    raw_embeddings = result.get("embeddings")
    embeddings = list(raw_embeddings) if raw_embeddings is not None else []
    return {
        "ids": list(result.get("ids") or []),
        "documents": list(result.get("documents") or []),
        "metadatas": list(result.get("metadatas") or []),
        "embeddings": embeddings,
    }


def build_unified_index(*, dry_run: bool = False) -> int:
    """Merge learning_notes + job_descriptions into the unified knowledge collection."""

    client = chromadb.PersistentClient(path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR))

    note_data = _read_collection(client, NOTE_COLLECTION_NAME)
    jd_data = _read_collection(client, JD_COLLECTION_NAME)
    print(
        f"读取完成：{NOTE_COLLECTION_NAME}={len(note_data['ids'])} 块, "
        f"{JD_COLLECTION_NAME}={len(jd_data['ids'])} 条"
    )

    # 构造统一集合的写入数据
    unified_ids: list[str] = []
    unified_documents: list[str] = []
    unified_embeddings: list[list[float]] = []
    unified_metadatas: list[dict] = []

    # 笔记：metadata 加 doc_type=note，保留原 source/title_path
    for index, chunk_id in enumerate(note_data["ids"]):
        metadata = dict(note_data["metadatas"][index] or {})
        metadata["doc_type"] = "note"
        unified_ids.append(f"note:{chunk_id}")
        unified_documents.append(str(note_data["documents"][index] or ""))
        unified_embeddings.append(list(note_data["embeddings"][index]))
        unified_metadatas.append(metadata)

    # JD：metadata 加 doc_type=jd，保留 parent_id/child_type 等
    for index, chunk_id in enumerate(jd_data["ids"]):
        metadata = dict(jd_data["metadatas"][index] or {})
        metadata["doc_type"] = "jd"
        unified_ids.append(f"jd:{chunk_id}")
        unified_documents.append(str(jd_data["documents"][index] or ""))
        unified_embeddings.append(list(jd_data["embeddings"][index]))
        unified_metadatas.append(metadata)

    print(f"统一集合待写入：{len(unified_ids)} 条（note={len(note_data['ids'])} + jd={len(jd_data['ids'])}）")
    if dry_run:
        print("dry-run：不执行写入")
        return 0

    # 删除旧统一集合（如果存在），重建
    try:
        client.delete_collection(UNIFIED_COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=UNIFIED_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    written = 0
    for start in range(0, len(unified_ids), BATCH_SIZE):
        end = start + BATCH_SIZE
        collection.upsert(
            ids=unified_ids[start:end],
            documents=unified_documents[start:end],
            embeddings=unified_embeddings[start:end],
            metadatas=unified_metadatas[start:end],
        )
        written += end - start
        print(f"  已写入 {written}/{len(unified_ids)}")

    final_count = collection.count()
    print(f"统一集合 {UNIFIED_COLLECTION_NAME} 构建完成：{final_count} 条")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the unified knowledge collection from existing indexes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be merged without writing.",
    )
    args = parser.parse_args()
    try:
        return build_unified_index(dry_run=args.dry_run)
    except Exception as exc:
        print(f"构建统一索引失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())