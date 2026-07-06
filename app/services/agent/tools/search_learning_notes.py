"""Search indexed learning notes for Tutor Agent tool calling."""

from __future__ import annotations

from typing import Any

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.repositories.knowledge_repository import KnowledgeHit, KnowledgeRepository
from app.services.rag_settings import RAG_TOP_K, SIMILARITY_THRESHOLD


MAX_TOOL_LIMIT = 5
DEFAULT_TOOL_LIMIT = RAG_TOP_K

_repository: KnowledgeRepository | None = None
_embedding_client: EmbeddingClient | None = None


def search_learning_notes(
    query: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """检索用户自己的学习笔记，并返回模型友好的结构化结果。"""

    if not isinstance(query, str) or not query.strip():
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "query must be a non-empty string.",
        }

    safe_limit = _clamp_limit(limit)
    repository = _get_repository()
    if repository.count() == 0:
        return {
            "ok": False,
            "error": "index_not_built",
            "message": "请先运行 scripts/build_knowledge_index.py 构建学习笔记索引。",
        }

    try:
        query_embedding = _get_embedding_client().embed_texts([query.strip()])[0]
    except (EmbeddingError, IndexError) as exc:
        return {
            "ok": False,
            "error": "embedding_failed",
            "message": f"embedding failed: {exc}",
        }

    hits = [
        hit
        for hit in repository.search(query_embedding=query_embedding, top_k=safe_limit)
        if hit.similarity >= SIMILARITY_THRESHOLD
    ]
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

