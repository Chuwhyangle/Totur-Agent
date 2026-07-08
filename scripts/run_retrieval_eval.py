"""Run v0.4 retrieval evaluation against the local Chroma knowledge index."""

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
from app.services.hybrid_retriever import hybrid_search
from app.services.rag_settings import RAG_TOP_K, SIMILARITY_THRESHOLD
from app.services.retrieval_eval import (
    evaluate_cases,
    load_eval_cases,
    manual_cosine_check,
)


DEFAULT_EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument(
        "--mode",
        choices=["vector", "hybrid"],
        default="vector",
        help="Retrieval mode to evaluate.",
    )
    parser.add_argument("--top-k", type=int, default=RAG_TOP_K)
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument(
        "--threshold-sweep",
        action="store_true",
        help="Evaluate several threshold values in the same run.",
    )
    parser.add_argument(
        "--sweep-values",
        default="0.25,0.35,0.45,0.55,0.65,0.75",
        help="Comma-separated threshold values used with --threshold-sweep.",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON output.")
    args = parser.parse_args()

    try:
        cases = load_eval_cases(args.eval_file)
        repository = KnowledgeRepository()
        if repository.count() == 0:
            raise RuntimeError("knowledge index is empty; run scripts/build_knowledge_index.py first.")

        embedding_client = EmbeddingClient(config=load_embedding_config())

        cached_hits = {}

        def search(query: str, top_k: int):
            if query in cached_hits:
                return cached_hits[query][:top_k]

            query_embedding = embedding_client.embed_texts([query])[0]
            if args.mode == "hybrid":
                hits = hybrid_search(
                    repository=repository,
                    query=query,
                    query_embedding=query_embedding,
                    top_k=args.top_k,
                )
            else:
                hits = repository.search(query_embedding=query_embedding, top_k=args.top_k)
            cached_hits[query] = hits
            return hits[:top_k]

        summary = evaluate_cases(
            cases=cases,
            search=search,
            top_k=args.top_k,
            threshold=args.threshold,
        )
        summary["mode"] = args.mode
        if args.threshold_sweep:
            summary["threshold_sweep"] = _run_threshold_sweep(
                cases=cases,
                search=search,
                top_k=args.top_k,
                sweep_values=_parse_sweep_values(args.sweep_values),
            )
        summary["manual_cosine_check"] = _run_manual_cosine_check(
            cases=cases,
            repository=repository,
            embedding_client=embedding_client,
        )
    except (RuntimeError, EmbeddingError, ValueError, OSError) as exc:
        print(f"检索评测失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_summary(summary)

    return 0


def _parse_sweep_values(raw_values: str) -> list[float]:
    """Parse comma-separated threshold values."""

    values = []
    for raw_value in raw_values.split(","):
        stripped = raw_value.strip()
        if stripped:
            values.append(float(stripped))

    if not values:
        raise ValueError("at least one sweep value is required.")

    return values


def _run_threshold_sweep(
    cases,
    search,
    top_k: int,
    sweep_values: list[float],
) -> list[dict]:
    """Run metric calculation for several thresholds using cached search hits."""

    rows = []
    for threshold in sweep_values:
        metrics = evaluate_cases(
            cases=cases,
            search=search,
            top_k=top_k,
            threshold=threshold,
        )["metrics"]
        rows.append(
            {
                "threshold": threshold,
                "recall_at_k": metrics["recall_at_k"],
                "mrr": metrics["mrr"],
                "negative_accuracy": metrics["negative_accuracy"],
                "overall_accuracy": metrics["overall_accuracy"],
            }
        )

    return rows


def _run_manual_cosine_check(
    cases,
    repository: KnowledgeRepository,
    embedding_client: EmbeddingClient,
) -> dict:
    """对第一条正例做一次手算 cosine 和 Chroma top-1 对拍。"""

    positive_case = next((case for case in cases if not case.is_negative), None)
    if positive_case is None:
        return {"status": "skipped", "message": "no positive eval case found."}

    query_embedding = embedding_client.embed_texts([positive_case.query])[0]
    chroma_hits = repository.search(query_embedding=query_embedding, top_k=1)
    entries = repository.list_entries(include_embeddings=True)
    result = manual_cosine_check(
        query_embedding=query_embedding,
        entries=entries,
        chroma_hits=chroma_hits,
    )
    result["case_id"] = positive_case.case_id
    result["query"] = positive_case.query
    return result


def _print_summary(summary: dict) -> None:
    """Print a compact human-readable eval report."""

    metrics = summary["metrics"]
    print("v0.4 retrieval eval")
    print(f"mode={summary.get('mode', 'vector')}")
    print(
        "cases={total_cases} positives={positive_cases} negatives={negative_cases} "
        "top_k={top_k} threshold={threshold}".format(**metrics)
    )
    print(f"recall@k={metrics['recall_at_k']:.4f}")
    print(f"MRR={metrics['mrr']:.4f}")
    print(f"negative_accuracy={metrics['negative_accuracy']:.4f}")
    print(f"overall_accuracy={metrics['overall_accuracy']:.4f}")

    cosine_check = summary.get("manual_cosine_check", {})
    print(
        "manual_cosine_check={status} case={case_id} delta={delta}".format(
            status=cosine_check.get("status"),
            case_id=cosine_check.get("case_id", "-"),
            delta=cosine_check.get("similarity_delta", "-"),
        )
    )

    failures = [result for result in summary["results"] if not result["passed"]]
    if failures:
        print("failures:")
        for result in failures[:20]:
            print(
                "- {id}: expected={expected} hits={hits}".format(
                    id=result["id"],
                    expected=result["expected_sources"] or "[]",
                    hits=result["hit_sources"],
                )
            )
    else:
        print("failures: none")

    if "threshold_sweep" in summary:
        print("threshold_sweep:")
        for row in summary["threshold_sweep"]:
            print(
                "- threshold={threshold:.2f} recall@k={recall_at_k:.4f} "
                "MRR={mrr:.4f} negative_accuracy={negative_accuracy:.4f} "
                "overall_accuracy={overall_accuracy:.4f}".format(**row)
            )


if __name__ == "__main__":
    raise SystemExit(main())
