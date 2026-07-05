"""Search saved interview JD records for tool calling."""

from __future__ import annotations

import re
from typing import Any

from app.db.models import InterviewJDRecord
from app.repositories.interview_jd_repository import list_all_interview_jds


MAX_TOOL_LIMIT = 5
DEFAULT_TOOL_LIMIT = 3

FIELD_WEIGHTS = {
    "title": 4,
    "role_family": 4,
    "core_skills": 3,
    "keywords": 3,
    "interview_focus": 3,
    "responsibilities": 2,
    "must_have": 2,
    "preferred_skills": 2,
    "bonus_skills": 2,
    "raw_text": 1,
}

KNOWN_TERMS = {
    "ai",
    "llm",
    "rag",
    "mcp",
    "a2a",
    "api",
    "nl2sql",
    "vue",
    "java",
    "python",
    "fastapi",
    "agent",
    "langchain",
    "langgraph",
    "function calling",
    "工具调用",
    "智能体",
    "全栈",
    "后端",
    "工作流",
    "上下文",
    "提示词",
}


def search_interview_jds(query: str, limit: int = DEFAULT_TOOL_LIMIT) -> dict[str, Any]:
    """Search saved JD records and return a model-friendly tool result."""

    if not isinstance(query, str) or not query.strip():
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "query must be a non-empty string.",
        }

    safe_limit = _clamp_limit(limit)
    terms = _query_terms(query)
    records = list_all_interview_jds()
    scored_records = []

    for record in records:
        match_score, matched_fields = _score_record(record, terms)
        if match_score > 0:
            scored_records.append((match_score, matched_fields, record))

    scored_records.sort(
        key=lambda item: (item[0], item[2].updated_at, item[2].title),
        reverse=True,
    )
    items = [
        _item_from_record(record, match_score, matched_fields, terms)
        for match_score, matched_fields, record in scored_records[:safe_limit]
    ]
    result: dict[str, Any] = {
        "ok": True,
        "query": query,
        "items": items,
        "summary": {
            "returned_count": len(items),
            "searched_count": len(records),
        },
    }

    if not items:
        result["message"] = "No interview JD matched the query."

    return result


def _query_terms(query: str) -> list[str]:
    normalized = _normalize(query)
    raw_terms = re.findall(r"[a-z0-9+#.]+|[\u4e00-\u9fff]+", normalized)
    terms = {
        term
        for term in raw_terms
        if len(term) >= 2 or term in {"c", "r", "go", "ai"}
    }

    for known_term in KNOWN_TERMS:
        if known_term in normalized:
            terms.add(known_term)

    if not terms:
        terms.add(normalized)

    return sorted(terms, key=len, reverse=True)


def _score_record(
    record: InterviewJDRecord,
    terms: list[str],
) -> tuple[int, list[str]]:
    score = 0
    matched_fields = []

    for field_name, weight in FIELD_WEIGHTS.items():
        field_text = _field_text(getattr(record, field_name))
        field_matched = False

        for term in terms:
            if term in field_text:
                score += weight
                field_matched = True

        if field_matched:
            matched_fields.append(field_name)

    return score, matched_fields


def _item_from_record(
    record: InterviewJDRecord,
    match_score: int,
    matched_fields: list[str],
    terms: list[str],
) -> dict[str, Any]:
    return {
        "title": record.title,
        "role_family": record.role_family,
        "seniority": record.seniority,
        "match_score": match_score,
        "matched_fields": matched_fields,
        "responsibilities": record.responsibilities,
        "must_have": record.must_have,
        "core_skills": record.core_skills,
        "preferred_skills": record.preferred_skills,
        "bonus_skills": record.bonus_skills,
        "keywords": record.keywords,
        "interview_focus": record.interview_focus,
        "raw_text_excerpt": _excerpt(record.raw_text, terms),
    }


def _field_text(value: str | list[str] | None) -> str:
    if value is None:
        return ""

    if isinstance(value, list):
        return _normalize(" ".join(value))

    return _normalize(value)


def _normalize(value: str) -> str:
    return value.lower().strip()


def _clamp_limit(limit: int) -> int:
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = DEFAULT_TOOL_LIMIT

    return max(1, min(parsed_limit, MAX_TOOL_LIMIT))


def _excerpt(raw_text: str, terms: list[str], max_length: int = 140) -> str:
    normalized_raw_text = _normalize(raw_text)
    first_match_index = -1

    for term in terms:
        term_index = normalized_raw_text.find(term)
        if term_index != -1 and (
            first_match_index == -1 or term_index < first_match_index
        ):
            first_match_index = term_index

    if first_match_index == -1:
        excerpt = raw_text[:max_length]
    else:
        start = max(0, first_match_index - 30)
        excerpt = raw_text[start : start + max_length]

    if len(raw_text) > len(excerpt):
        return f"{excerpt.strip()}..."

    return excerpt.strip()
