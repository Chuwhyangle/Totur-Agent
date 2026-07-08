"""RAG 检索评测工具函数。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from app.repositories.knowledge_repository import KnowledgeEntry, KnowledgeHit


@dataclass(frozen=True)
class RetrievalEvalCase:
    """一条检索评测用例。"""

    case_id: str
    query: str
    expected_sources: list[str]
    expected_title_keywords: list[str]
    notes: str = ""

    @property
    def is_negative(self) -> bool:
        """没有期望来源的用例就是负例。"""

        return not self.expected_sources


SearchFunc = Callable[[str, int], list[KnowledgeHit]]


def load_eval_cases(path: Path) -> list[RetrievalEvalCase]:
    """从 JSONL 文件读取检索评测集。"""

    cases: list[RetrievalEvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue

        payload = json.loads(line)
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError(f"case on line {line_number} must include a query.")

        case_id = str(payload.get("id") or f"case_{line_number:03d}")
        expected_sources = [
            str(source)
            for source in payload.get("expected_sources", [])
            if str(source).strip()
        ]
        expected_title_keywords = [
            str(keyword)
            for keyword in payload.get("expected_title_keywords", [])
            if str(keyword).strip()
        ]
        cases.append(
            RetrievalEvalCase(
                case_id=case_id,
                query=query,
                expected_sources=expected_sources,
                expected_title_keywords=expected_title_keywords,
                notes=str(payload.get("notes") or ""),
            )
        )

    if not cases:
        raise ValueError(f"no eval cases found in {path}.")

    return cases


def evaluate_cases(
    cases: list[RetrievalEvalCase],
    search: SearchFunc,
    top_k: int,
    threshold: float,
) -> dict[str, Any]:
    """运行评测并返回 recall@k、MRR 和负例准确率。"""

    positive_total = 0
    positive_hits = 0
    reciprocal_rank_sum = 0.0
    negative_total = 0
    negative_correct = 0
    passed_total = 0
    results: list[dict[str, Any]] = []

    for case in cases:
        raw_hits = search(case.query, top_k)
        hits = [hit for hit in raw_hits if hit.similarity >= threshold]
        rank = _first_expected_rank(case, hits)

        if case.is_negative:
            negative_total += 1
            passed = not hits
            if passed:
                negative_correct += 1
        else:
            positive_total += 1
            passed = rank is not None
            if rank is not None:
                positive_hits += 1
                reciprocal_rank_sum += 1 / rank

        if passed:
            passed_total += 1

        results.append(
            {
                "id": case.case_id,
                "query": case.query,
                "expected_sources": case.expected_sources,
                "hit_sources": [hit.source for hit in hits],
                "rank": rank,
                "passed": passed,
                "negative": case.is_negative,
            }
        )

    metrics = {
        "total_cases": len(cases),
        "positive_cases": positive_total,
        "negative_cases": negative_total,
        "top_k": top_k,
        "threshold": threshold,
        "recall_at_k": _safe_divide(positive_hits, positive_total),
        "mrr": _safe_divide(reciprocal_rank_sum, positive_total),
        "negative_accuracy": _safe_divide(negative_correct, negative_total),
        "overall_accuracy": _safe_divide(passed_total, len(cases)),
    }
    return {"metrics": metrics, "results": results}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """手算 cosine similarity，用于和 Chroma cosine 结果对拍。"""

    if len(left) != len(right) or not left:
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot / (left_norm * right_norm)


def rank_entries_by_cosine(
    query_embedding: list[float],
    entries: list[KnowledgeEntry],
) -> list[tuple[KnowledgeEntry, float]]:
    """用手算 cosine 给所有条目排序。"""

    scored = [
        (entry, cosine_similarity(query_embedding, entry.embedding))
        for entry in entries
        if entry.embedding is not None
    ]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def manual_cosine_check(
    query_embedding: list[float],
    entries: list[KnowledgeEntry],
    chroma_hits: list[KnowledgeHit],
) -> dict[str, Any]:
    """比较手算 cosine top-1 与 Chroma top-1 是否一致。"""

    ranked = rank_entries_by_cosine(query_embedding, entries)
    if not ranked or not chroma_hits:
        return {
            "status": "skipped",
            "message": "no entries or Chroma hits available for cosine check.",
        }

    manual_entry, manual_similarity = ranked[0]
    chroma_hit = chroma_hits[0]
    matched = (
        manual_entry.source == chroma_hit.source
        and manual_entry.title_path == chroma_hit.title_path
    )
    return {
        "status": "ok" if matched else "mismatch",
        "manual_source": manual_entry.source,
        "manual_title_path": manual_entry.title_path,
        "manual_similarity": round(manual_similarity, 6),
        "chroma_source": chroma_hit.source,
        "chroma_title_path": chroma_hit.title_path,
        "chroma_similarity": round(chroma_hit.similarity, 6),
        "similarity_delta": round(abs(manual_similarity - chroma_hit.similarity), 6),
    }


def _first_expected_rank(
    case: RetrievalEvalCase,
    hits: list[KnowledgeHit],
) -> int | None:
    """返回第一个命中期望来源的 rank，从 1 开始。"""

    for index, hit in enumerate(hits, 1):
        if _hit_matches_case(case, hit):
            return index

    return None


def _hit_matches_case(case: RetrievalEvalCase, hit: KnowledgeHit) -> bool:
    """判断检索结果是否满足用例期望。"""

    if hit.source not in case.expected_sources:
        return False

    if not case.expected_title_keywords:
        return True

    haystack = f"{hit.title_path}\n{hit.content}".lower()
    return all(keyword.lower() in haystack for keyword in case.expected_title_keywords)


def _safe_divide(numerator: float, denominator: int) -> float:
    """避免没有正例或负例时除零。"""

    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 4)
