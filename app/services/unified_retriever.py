"""Unified retrieval over the merged `knowledge` Chroma collection.

方案 A（统一单集合）：一个集合装学习笔记 + 项目文档 + 面试 JD。
检索时一次 ANN 查询覆盖所有类型；命中 JD 子向量时通过 `source`
找回完整父 JD 文档。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.services.rag_settings import CHROMA_PERSIST_DIR, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UNIFIED_COLLECTION_NAME = "knowledge"

_client: Any | None = None
_embedding_client: EmbeddingClient | None = None


def unified_search(
    query: str,
    top_k: int = 3,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Search the unified knowledge collection and return model-friendly items.

    返回统一格式的检索结果，每条带 doc_type：
    - note：学习笔记/项目文档块
    - jd：完整 JD（从父文档读取）
    """

    if not isinstance(query, str) or not query.strip():
        return []
    if top_k <= 0:
        return []

    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    try:
        embedding_client = _get_embedding_client()
        query_embedding = embedding_client.embed_texts([query.strip()])[0]
    except (EmbeddingError, IndexError, RuntimeError):
        logger.warning("unified search embedding failed for query=%r", query)
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    items: list[dict[str, Any]] = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        safe_metadata = metadata or {}
        similarity = 1 - float(distance or 0)
        if similarity < threshold:
            continue
        item = _hit_to_item(
            content=str(document or ""),
            metadata=safe_metadata,
            similarity=similarity,
        )
        if item is not None:
            items.append(item)
    return items


def _hit_to_item(
    *,
    content: str,
    metadata: dict[str, Any],
    similarity: float,
) -> dict[str, Any] | None:
    """Convert one raw hit into a unified item, recovering full JD for jd hits."""

    doc_type = str(metadata.get("doc_type") or "note")
    source = str(metadata.get("source") or "")
    if not source:
        return None

    if doc_type == "jd":
        full_content = _read_jd_parent(source)
        if full_content is None:
            return None
        return {
            "doc_type": "jd",
            "source": source,
            "title_path": str(metadata.get("title") or source),
            "content": full_content,
            "similarity": round(similarity, 4),
            "evidence_kind": "jd",
            "company": str(metadata.get("company") or ""),
            "title": str(metadata.get("title") or ""),
            "parent_id": str(metadata.get("parent_id") or ""),
            "child_type": str(metadata.get("child_type") or ""),
        }

    return {
        "doc_type": "note",
        "source": source,
        "title_path": str(metadata.get("title_path") or ""),
        "content": content,
        "similarity": round(similarity, 4),
        "evidence_kind": "note",
    }


def _read_jd_parent(source: str) -> str | None:
    """Read the full JD markdown from corpus/JD by its source path."""

    path = PROJECT_ROOT / source
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        logger.warning("cannot read JD parent %s", source)
        return None


def _get_collection():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(PROJECT_ROOT / CHROMA_PERSIST_DIR)
        )
    try:
        return _client.get_collection(UNIFIED_COLLECTION_NAME)
    except Exception:
        return None


def _get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client