"""Evaluate v0.4 seed-context coverage against the retrieval eval set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.rag_seed_context import retrieve_seed_knowledge_context
from app.services.rag_settings import RAG_SEED_MAX_CHARS, RAG_SEED_TOP_K
from app.services.retrieval_eval import load_eval_cases


DEFAULT_EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Evaluate RAG seed-context coverage.")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--top-k", type=int, default=RAG_SEED_TOP_K)
    parser.add_argument("--max-chars", type=int, default=RAG_SEED_MAX_CHARS)
    parser.add_argument("--json", action="store_true", help="Print raw JSON output.")
    args = parser.parse_args()

    try:
        cases = load_eval_cases(args.eval_file)
        repository = KnowledgeRepository()
        if repository.count() == 0:
            raise RuntimeError("knowledge index is empty; run scripts/build_knowledge_index.py first.")

        embedding_client = EmbeddingClient(config=load_embedding_config())
        summary = evaluate_seed_contexts(
            cases=cases,
            repository=repository,
            embedding_client=embedding_client,
            top_k=args.top_k,
            max_chars=args.max_chars,
        )
    except (RuntimeError, EmbeddingError, ValueError, OSError) as exc:
        print(f"种子检索评测失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_summary(summary)

    return 0


def evaluate_seed_contexts(
    cases,
    repository: KnowledgeRepository,
    embedding_client: EmbeddingClient,
    top_k: int,
    max_chars: int,
) -> dict:
    """Build seed contexts and measure source coverage."""

    positive_total = 0
    positive_hits = 0
    negative_total = 0
    negative_correct = 0
    passed_total = 0
    context_lengths = []
    results = []

    for case in cases:
        context = retrieve_seed_knowledge_context(
            query=case.query,
            repository=repository,
            embedding_client=embedding_client,
            top_k=top_k,
            max_chars=max_chars,
        )
        context_text = context or ""
        context_lengths.append(len(context_text))

        if case.is_negative:
            negative_total += 1
            passed = context is None
            if passed:
                negative_correct += 1
        else:
            positive_total += 1
            passed = any(source in context_text for source in case.expected_sources)
            if passed:
                positive_hits += 1

        if passed:
            passed_total += 1

        results.append(
            {
                "id": case.case_id,
                "query": case.query,
                "expected_sources": case.expected_sources,
                "has_context": context is not None,
                "context_length": len(context_text),
                "passed": passed,
                "negative": case.is_negative,
            }
        )

    metrics = {
        "total_cases": len(cases),
        "positive_cases": positive_total,
        "negative_cases": negative_total,
        "top_k": top_k,
        "max_chars": max_chars,
        "seed_recall_at_k": _safe_divide(positive_hits, positive_total),
        "negative_context_accuracy": _safe_divide(negative_correct, negative_total),
        "overall_accuracy": _safe_divide(passed_total, len(cases)),
        "average_context_chars": round(sum(context_lengths) / len(context_lengths)),
        "max_context_chars_observed": max(context_lengths, default=0),
    }
    return {"metrics": metrics, "results": results}


def _print_summary(summary: dict) -> None:
    """Print a compact human-readable seed-context report."""

    metrics = summary["metrics"]
    print("v0.4 seed-context eval")
    print(
        "cases={total_cases} positives={positive_cases} negatives={negative_cases} "
        "top_k={top_k} max_chars={max_chars}".format(**metrics)
    )
    print(f"seed_recall@k={metrics['seed_recall_at_k']:.4f}")
    print(f"negative_context_accuracy={metrics['negative_context_accuracy']:.4f}")
    print(f"overall_accuracy={metrics['overall_accuracy']:.4f}")
    print(f"average_context_chars={metrics['average_context_chars']}")
    print(f"max_context_chars_observed={metrics['max_context_chars_observed']}")

    failures = [result for result in summary["results"] if not result["passed"]]
    if failures:
        print("failures:")
        for result in failures[:20]:
            print(
                "- {id}: expected={expected} has_context={has_context} chars={chars}".format(
                    id=result["id"],
                    expected=result["expected_sources"] or "[]",
                    has_context=result["has_context"],
                    chars=result["context_length"],
                )
            )
    else:
        print("failures: none")


def _safe_divide(numerator: float, denominator: int) -> float:
    """Avoid division by zero."""

    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 4)


if __name__ == "__main__":
    raise SystemExit(main())
