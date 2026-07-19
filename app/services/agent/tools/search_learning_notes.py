"""Search indexed learning notes for Tutor Agent tool calling."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.repositories.knowledge_repository import KnowledgeHit, KnowledgeRepository
from app.services.shard_router import ShardRouter
from app.services.hybrid_retriever import hybrid_search
from app.services.index_manifest import ManifestError, load_manifest
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    ENABLE_HYBRID_RETRIEVAL,
    ENABLE_SUBJECT_SHARDING,
    RAG_TOP_K,
    SIMILARITY_THRESHOLD,
)


MAX_TOOL_LIMIT = 5
DEFAULT_TOOL_LIMIT = RAG_TOP_K
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"

logger = logging.getLogger(__name__)

_repository: KnowledgeRepository | None = None
_router: ShardRouter | None = None
_embedding_client: EmbeddingClient | None = None
# Cache (mtime_ns, fingerprint) so a rebuilt index is picked up without restart.
_manifest_cache: tuple[int, str] | None = None


def search_learning_notes(
    query: str,
    limit: int | None = None,
    subject: str | None = None,
) -> dict[str, Any]:
    """检索用户自己的学习笔记，并返回模型友好的结构化结果。"""

    if not isinstance(query, str) or not query.strip():
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "query must be a non-empty string.",
        }

    safe_limit = _clamp_limit(limit)
    router = _get_router() if ENABLE_SUBJECT_SHARDING else None
    repository = _get_repository()
    if router is not None:
        index_count = sum(shard.repository.count() for shard in router.handles)
    else:
        index_count = repository.count()
    if index_count == 0:
        return {
            "ok": False,
            "error": "index_not_built",
            "message": "请先运行 scripts/build_knowledge_index.py 构建学习笔记索引。",
        }

    stripped_query = query.strip()
    try:
        query_embedding = _get_embedding_client().embed_texts([stripped_query])[0]
    except (EmbeddingError, IndexError) as exc:
        return {
            "ok": False,
            "error": "embedding_failed",
            "message": f"embedding failed: {exc}",
        }

    hits = _retrieve_hits(
        repository=repository,
        query=stripped_query,
        query_embedding=query_embedding,
        top_k=safe_limit,
        subject=subject,
        router=router,
    )
    # hybrid_search 分数已归一化到 0-1；阈值语义与 eval 一致，允许强 lexical 命中通过。
    hits = [hit for hit in hits if hit.similarity >= SIMILARITY_THRESHOLD]
    items = [_item_from_hit(hit) for hit in hits]
    result: dict[str, Any] = {
        "ok": True,
        "found": bool(items),
        "query": query,
        "count": len(items),
        "results": items,
        # 现有 ReAct trace 读取 items；保留 results 语义的同时给它一个兼容别名。
        "items": items,
        "summary": {
            "returned_count": len(items),
        },
    }

    if not items:
        result["message"] = "未找到相关笔记。"

    return result


def _retrieve_hits(
    *,
    repository: KnowledgeRepository,
    query: str,
    query_embedding: list[float],
    top_k: int,
    subject: str | None = None,
    router: ShardRouter | None = None,
) -> list[KnowledgeHit]:
    """Route through subject shards when enabled, otherwise preserve single-index behavior."""

    if router is not None:
        return router.search(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            subject=subject,
        )

    if ENABLE_HYBRID_RETRIEVAL:
        fingerprint = _get_manifest_fingerprint()
        if fingerprint is not None:
            return hybrid_search(
                repository=repository,
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
                fingerprint=fingerprint,
            )

    return repository.search(query_embedding=query_embedding, top_k=top_k)


def _get_router() -> ShardRouter | None:
    """Load subject shards lazily; return None when deployment has no shards yet."""

    global _router
    if _router is not None:
        return _router

    repository = _get_repository()
    candidate = ShardRouter.from_client(repository.client)
    if not candidate.handles:
        logger.warning(
            "subject sharding is enabled but no %s collections were found; "
            "falling back to the legacy single collection",
            "learning_notes_",
        )
        return None
    _router = candidate
    return _router


def _get_manifest_fingerprint() -> str | None:
    """Load the index fingerprint with mtime-based cache refresh.

    Returns None (and logs a warning) when the manifest is missing or invalid so
    serving can fall back to pure vector search without crashing.
    """

    global _manifest_cache

    try:
        mtime_ns = MANIFEST_PATH.stat().st_mtime_ns
    except OSError:
        logger.warning(
            "index manifest missing at %s; falling back to pure vector search",
            MANIFEST_PATH,
        )
        _manifest_cache = None
        return None

    if _manifest_cache is not None and _manifest_cache[0] == mtime_ns:
        return _manifest_cache[1]

    try:
        fingerprint = load_manifest(MANIFEST_PATH).fingerprint
    except ManifestError as exc:
        logger.warning(
            "index manifest invalid at %s (%s); falling back to pure vector search",
            MANIFEST_PATH,
            exc,
        )
        _manifest_cache = None
        return None

    _manifest_cache = (mtime_ns, fingerprint)
    return fingerprint


def _item_from_hit(hit: KnowledgeHit) -> dict[str, Any]:
    """把 repository 命中结果压缩成工具 observation。"""

    title = hit.title_path or hit.source
    return {
        "title": title,
        "content": hit.content,
        "source": hit.source,
        "title_path": hit.title_path,
        "similarity": round(hit.similarity, 4),
        "match_score": round(hit.similarity * 100),
        "raw_text_excerpt": _excerpt(hit.content),
    }


def _excerpt(content: str, max_length: int = 140) -> str:
    """生成前端调试区可读的短摘录。"""

    text = content.strip()
    if len(text) <= max_length:
        return text

    return f"{text[:max_length].strip()}..."


def _clamp_limit(limit: int | None) -> int:
    """限制模型传入的 limit，避免一次塞入过多 observation。"""

    try:
        parsed_limit = int(limit) if limit is not None else DEFAULT_TOOL_LIMIT
    except (TypeError, ValueError):
        parsed_limit = DEFAULT_TOOL_LIMIT

    return max(1, min(parsed_limit, MAX_TOOL_LIMIT))


def _get_repository() -> KnowledgeRepository:
    """懒加载 repository，测试中可 monkeypatch 替换。"""

    global _repository
    if _repository is None:
        _repository = KnowledgeRepository()

    return _repository


def _get_embedding_client() -> EmbeddingClient:
    """懒加载 embedding client，避免导入工具时立即读取环境变量。"""

    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()

    return _embedding_client
