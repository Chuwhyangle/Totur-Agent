"""Search documents the user uploaded in the current conversation.

FR-3：附件检索工具化，与笔记/JD/联网并列第四条路由。
user_id / session_id / attachment_ids 由执行器从请求上下文注入，
不进工具 schema——权限参数绝不暴露给 LLM。
"""

from __future__ import annotations

import time
from typing import Any

from app.db import trace_db
from app.services import timings
from app.services.documents.attachment_retrieval_service import (
    AttachmentEvidence,
    AttachmentNoRelevantEvidenceError,
    AttachmentRetrievalService,
    attachment_source_title,
    build_attachment_context,
)
from app.services.documents.settings import DEFAULT_TEMP_DOCUMENT_CONTEXT_MAX_CHARS


DEFAULT_TOOL_LIMIT = 3
MAX_TOOL_LIMIT = 5


def search_attachments(
    query: str,
    limit: int | None = None,
    *,
    user_id: str | None = None,
    session_id: int | None = None,
    attachment_ids: list[str] | None = None,
    attachment_retrieval_service: AttachmentRetrievalService | None = None,
    context_max_chars: int | None = None,
) -> dict[str, Any]:
    """Search documents the user uploaded in the current conversation.

    返回与 search_learning_notes 兼容的结构：{ok, found, items, summary}。
    items 中每项带 evidence_id（attachment_N），与 leder / 引用契约一致。
    """

    if not isinstance(query, str) or not query.strip():
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "query must be a non-empty string.",
        }

    # 权限参数由执行器注入；缺失时返回明确错误（不进 schema 的兜底）。
    if not user_id or session_id is None or not attachment_ids:
        return {
            "ok": False,
            "error": "missing_request_context",
            "message": "attachment search requires request context (user/session/attachment).",
        }

    safe_limit = _clamp_limit(limit)
    service = attachment_retrieval_service or AttachmentRetrievalService()
    max_context_chars = context_max_chars or getattr(
        service,
        "context_max_chars",
        DEFAULT_TEMP_DOCUMENT_CONTEXT_MAX_CHARS,
    )

    retrieval_started_at = time.perf_counter()
    try:
        evidence: list[AttachmentEvidence] = service.retrieve(
            user_id=user_id,
            session_id=session_id,
            attachment_ids=attachment_ids,
            query=query.strip(),
        )
    except AttachmentNoRelevantEvidenceError:
        trace_db.save_retrieval_event(
            trace_id=timings.get_trace_id(),
            query=query.strip(),
            collection="attachment",
            top_k=safe_limit,
            hit_count=0,
            top_score=0.0,
            min_score=0.0,
            passed=0,
            cost_ms=int((time.perf_counter() - retrieval_started_at) * 1000),
        )
        return {
            "ok": True,
            "found": False,
            "query": query,
            "count": 0,
            "items": [],
            "message": "在所选附件中没有检索到与当前问题足够相关的内容。",
            "summary": {"returned_count": 0},
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "attachment_retrieval_failed",
            "message": f"附件检索失败：{exc}",
        }

    trace_db.save_retrieval_event(
        trace_id=timings.get_trace_id(),
        query=query.strip(),
        collection="attachment",
        top_k=safe_limit,
        hit_count=len(evidence),
        top_score=max((item.similarity for item in evidence), default=0.0),
        min_score=min((item.similarity for item in evidence), default=0.0),
        passed=int(bool(evidence)),
        cost_ms=int((time.perf_counter() - retrieval_started_at) * 1000),
    )

    # 截断到 safe_limit 条，保持 observation 可控。
    evidence = evidence[:safe_limit]
    items = [
        {
            "evidence_id": item.evidence_id,
            "title": attachment_source_title(item),
            "document_id": item.document_id,
            "original_filename": item.original_filename,
            "page_start": item.page_start,
            "page_end": item.page_end,
            "locator_unit": item.locator_unit,
            "locator": item.locator,
            "content": item.text,
            "similarity": round(item.similarity, 4),
            "match_score": round(item.similarity * 100),
            "raw_text_excerpt": _excerpt(item.text),
        }
        for item in evidence
    ]

    return {
        "ok": True,
        "found": bool(items),
        "query": query,
        "count": len(items),
        "items": items,
        "summary": {"returned_count": len(items)},
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
