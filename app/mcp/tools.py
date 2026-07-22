"""Business tool wrappers exposed by the Tutor MCP server."""
from __future__ import annotations
import json
from typing import Any
from app.services.agent.tools.interview_jd_search import search_interview_jds
from app.services.agent.tools.score_jd_skill_fit import score_jd_skill_fit
from app.services.agent.tools.search_learning_notes import search_learning_notes
from app.services.tool_metrics import observe_tool_call

def tool_search_learning_notes(query: str, limit: int = 3, subject: str | None = None) -> dict[str, Any]:
    """Search local learning notes through the existing RAG stack."""
    with observe_tool_call("search_learning_notes", "mcp_server") as metric:
        kwargs: dict[str, Any] = {"query": query, "limit": limit}
        if subject is not None:
            kwargs["subject"] = subject
        result = search_learning_notes(**kwargs)
        metric.set_ok(bool(result.get("ok")))
        return result

def tool_interview_jd_search(query: str, limit: int = 3) -> dict[str, Any]:
    """Search saved interview job descriptions."""
    with observe_tool_call("interview_jd_search", "mcp_server") as metric:
        result = search_interview_jds(query=query, limit=limit)
        metric.set_ok(bool(result.get("ok")))
        return result

def tool_score_jd_skill_fit(skills: list[dict[str, Any]] | str, target_role: str | None = None) -> dict[str, Any]:
    """Score JD skill fit from structured skill judgments."""
    with observe_tool_call("score_jd_skill_fit", "mcp_server") as metric:
        parsed_skills = skills
        if isinstance(skills, str):
            try:
                parsed_skills = json.loads(skills)
            except json.JSONDecodeError:
                metric.set_ok(False)
                return {"ok": False, "error": "invalid_arguments", "message": "skills must be a JSON array of skill judgments."}
        result = score_jd_skill_fit(skills=parsed_skills, target_role=target_role)
        metric.set_ok(bool(result.get("ok")))
        return result

def tool_generate_quiz(query: str, count: int = 3, subject: str | None = None) -> dict[str, Any]:
    """Create source-linked quiz questions from retrieved learning notes."""
    with observe_tool_call("generate_quiz", "mcp_server") as metric:
        safe_count = max(1, min(int(count or 3), 5))
        kwargs: dict[str, Any] = {"query": query, "limit": safe_count}
        if subject is not None:
            kwargs["subject"] = subject
        retrieval = search_learning_notes(**kwargs)
        if not retrieval.get("ok"):
            metric.set_ok(False)
            return retrieval
        results = retrieval.get("results") or retrieval.get("items") or []
        quiz_items: list[dict[str, Any]] = []
        for index, item in enumerate(results[:safe_count], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("source") or f"note-{index}")
            excerpt = str(item.get("raw_text_excerpt") or item.get("content") or "").strip()
            source = str(item.get("source") or title)
            quiz_items.append({
                "id": f"quiz_{index}",
                "prompt": "阅读下面的笔记摘录，说明核心概念、适用边界，并给出一个实践场景：\n\n" + excerpt,
                "source": source,
                "title": title,
                "checkpoints": ["用自己的话解释核心概念", "指出至少一个边界或风险", "给出一个可执行的实践示例"],
            })
        metric.set_ok(True)
        result: dict[str, Any] = {
            "ok": True,
            "found": bool(quiz_items),
            "query": query,
            "count": len(quiz_items),
            "items": quiz_items,
            "summary": {"returned_count": len(quiz_items)},
        }
        if not quiz_items:
            result["message"] = "未找到可用于出题的相关笔记。"
        return result
