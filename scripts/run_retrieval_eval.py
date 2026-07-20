"""Run reproducible retrieval evaluation against a frozen Chroma index."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
import sys
import time
import statistics

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.config import Settings
from chromadb.errors import ChromaError

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.shard_router import ShardHandle, ShardRouter
from app.services.hybrid_retriever import hybrid_search
from app.services.reranking import RerankingService
from app.services.index_manifest import (
    IndexManifest,
    ManifestError,
    load_manifest,
)
from app.services.knowledge_index_builder import (
    IndexBuildResult,
    build_knowledge_index,
)
from app.services.rag_settings import (
    CHROMA_PERSIST_DIR,
    KNOWLEDGE_COLLECTION_NAME,
    collection_name_for_subject,
    subject_from_source,
    RAG_TOP_K,
    RERANK_CANDIDATE_K,
    SIMILARITY_THRESHOLD,
)
from app.services.retrieval_eval import (
    evaluate_cases,
    load_eval_cases,
    manual_cosine_check,
)


DEFAULT_EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"
DEFAULT_CORPUS_ROOT = PROJECT_ROOT / "tests" / "data" / "corpus"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest.json"


def main() -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--use-existing-index",
        action="store_true",
        help="Evaluate the persistent local index instead of rebuilding frozen corpus.",
    )
    parser.add_argument(
        "--mode",
        choices=["vector", "hybrid"],
        default="vector",
        help="Retrieval mode to evaluate.",
    )
    parser.add_argument(
        "--routing",
        choices=["baseline", "routed", "broadcast"],
        default="baseline",
        help="Evaluate the legacy single index, subject routing, or broadcast fan-out.",
    )
    parser.add_argument("--top-k", type=int, default=RAG_TOP_K)
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Batch-rerank thresholded retrieval candidates before scoring metrics.",
    )
    parser.add_argument(
        "--rerank-candidate-k",
        type=int,
        default=RERANK_CANDIDATE_K,
        help="Candidate pool size used when --rerank is enabled.",
    )
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
        config = load_embedding_config()
        embedding_client = EmbeddingClient(config=config)

        router = None
        shard_results = []
        if args.use_existing_index:
            repository = KnowledgeRepository()
            if args.routing == "baseline":
                manifest = load_manifest(DEFAULT_MANIFEST_PATH)
                validate_existing_index_identity(
                    repository_count=repository.count(),
                    manifest=manifest,
                    embedding_model=config.model,
                )
            else:
                router = ShardRouter.from_client(repository.client)
                if not router.handles:
                    raise ManifestError("no subject shard collections found for routed evaluation")
                manifest = _load_first_shard_manifest(router)
                validate_existing_index_identity(
                    repository_count=sum(shard.repository.count() for shard in router.handles),
                    manifest=manifest,
                    embedding_model=config.model,
                )
        else:
            repository = KnowledgeRepository(
                client=chromadb.EphemeralClient(
                    settings=Settings(anonymized_telemetry=False)
                )
            )
            if args.routing == "baseline":
                result = build_frozen_evaluation_index(
                    corpus_root=args.corpus_root,
                    repository=repository,
                    embedding_client=embedding_client,
                )
                manifest = result.manifest
            else:
                router, shard_results = build_frozen_evaluation_shards(
                    corpus_root=args.corpus_root,
                    client=repository.client,
                    embedding_client=embedding_client,
                    embedding_model=config.model,
                )
                manifest = shard_results[0].manifest

        if args.top_k <= 0:
            raise ValueError("top-k must be positive")
        if args.rerank_candidate_k <= 0:
            raise ValueError("rerank-candidate-k must be positive")

        retrieval_top_k = args.rerank_candidate_k if args.rerank else args.top_k
        cached_hits: dict[tuple[str, str, str | None], list] = {}
        latencies_ms: list[float] = []
        rerank_latencies_ms: list[float] = []
        rerank_fallback_count = 0
        rerank_applied_count = 0
        rerank_provider: str | None = None
        rerank_model: str | None = None
        rerank_traces: dict[tuple[str, str | None], dict] = {}
        reranking_service = RerankingService(enabled=True) if args.rerank else None

        def retrieve(query: str, subject: str | None = None):
            route_subject = subject if args.routing == "routed" else None
            cache_key = (query, args.routing, route_subject)
            if cache_key in cached_hits:
                return cached_hits[cache_key]

            started = time.perf_counter()
            query_embedding = embedding_client.embed_texts([query])[0]
            validate_query_embedding_dimensions(
                query_embedding=query_embedding,
                manifest=manifest,
            )
            if router is not None and router.handles:
                hits = router.search(
                    query=query,
                    query_embedding=query_embedding,
                    top_k=retrieval_top_k,
                    subject=route_subject,
                )
            elif args.mode == "hybrid":
                hits = hybrid_search(
                    repository=repository,
                    query=query,
                    query_embedding=query_embedding,
                    top_k=retrieval_top_k,
                    fingerprint=manifest.fingerprint,
                )
            else:
                hits = repository.search(
                    query_embedding=query_embedding,
                    top_k=retrieval_top_k,
                )
            latencies_ms.append((time.perf_counter() - started) * 1000)
            cached_hits[cache_key] = hits
            return hits

        def make_search(active_threshold: float, *, collect: bool):
            def search(query: str, top_k: int, subject: str | None = None):
                nonlocal rerank_fallback_count
                nonlocal rerank_applied_count
                nonlocal rerank_provider
                nonlocal rerank_model

                raw_hits = retrieve(query, subject)
                if reranking_service is None:
                    return raw_hits[:top_k]

                thresholded_hits = [
                    hit for hit in raw_hits if hit.similarity >= active_threshold
                ]
                outcome = reranking_service.rerank(
                    query,
                    thresholded_hits,
                    top_n=top_k,
                )
                if collect:
                    if outcome.latency_ms is not None:
                        rerank_latencies_ms.append(float(outcome.latency_ms))
                    if outcome.fallback_reason is not None:
                        rerank_fallback_count += 1
                    if outcome.applied:
                        rerank_applied_count += 1
                    rerank_provider = outcome.provider or rerank_provider
                    rerank_model = outcome.model or rerank_model
                    route_subject = subject if args.routing == "routed" else None
                    rerank_traces[(query, route_subject)] = {
                        "before_hits": thresholded_hits,
                        "after_hits": outcome.hits,
                        "applied": outcome.applied,
                        "fallback_reason": outcome.fallback_reason,
                    }
                return outcome.hits

            return search

        search = make_search(args.threshold, collect=True)
        summary = evaluate_cases(
            cases=cases,
            search=search,
            top_k=args.top_k,
            threshold=args.threshold,
        )
        summary["mode"] = args.mode
        summary["routing"] = args.routing
        summary["latency_ms"] = _latency_summary(latencies_ms)
        summary["retrieval_latency_ms"] = summary["latency_ms"]
        if args.rerank:
            _attach_rerank_case_traces(
                summary=summary,
                cases=cases,
                traces=rerank_traces,
                routing=args.routing,
            )
            summary["reranking"] = {
                "enabled": True,
                "candidate_k": args.rerank_candidate_k,
                "provider": rerank_provider,
                "model": rerank_model,
                "latency_ms": _rerank_latency_summary(rerank_latencies_ms),
                "applied_count": rerank_applied_count,
                "fallback_count": rerank_fallback_count,
                "cost": {
                    "currency": "USD",
                    "per_request": None,
                    "total": None,
                    "note": "provider usage/cost was not supplied by the generic protocol",
                },
            }
        else:
            summary["reranking"] = {
                "enabled": False,
                "candidate_k": None,
                "provider": None,
                "model": None,
                "latency_ms": _rerank_latency_summary([]),
                "applied_count": 0,
                "fallback_count": 0,
            }
        attach_manifest_summary(summary, manifest)
        if shard_results:
            summary["shards"] = [
                {
                    "subject": result.manifest.corpus_root,
                    "collection": result.manifest.collection_name,
                    "fingerprint": result.manifest.fingerprint,
                    "files": result.manifest.file_count,
                    "chunks": result.manifest.chunk_count,
                }
                for result in shard_results
            ]
        if args.threshold_sweep:
            summary["threshold_sweep"] = _run_threshold_sweep(
                cases=cases,
                search=search,
                top_k=args.top_k,
                sweep_values=_parse_sweep_values(args.sweep_values),
                search_factory=(
                    (lambda threshold: make_search(threshold, collect=False))
                    if args.rerank
                    else None
                ),
            )
        summary["manual_cosine_check"] = _run_manual_cosine_check(
            cases=cases,
            repository=repository,
            embedding_client=embedding_client,
            manifest=manifest,
        )
    except (
        ChromaError,
        RuntimeError,
        EmbeddingError,
        ManifestError,
        ValueError,
        OSError,
    ) as exc:
        print(f"检索评测失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_summary(summary)

    return 0


def build_frozen_evaluation_shards(
    *,
    corpus_root: Path,
    client,
    embedding_client: EmbeddingClient,
    embedding_model: str,
) -> tuple[ShardRouter, list[IndexBuildResult]]:
    """Build the frozen corpus into logical subject collections for routing eval."""

    root = Path(corpus_root)
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            source = path.relative_to(root).as_posix()
            groups[subject_from_source(source)].append(Path(source))
    if not groups:
        raise ValueError(f"no markdown files found under {root}")

    handles: list[ShardHandle] = []
    results: list[IndexBuildResult] = []
    for subject in sorted(groups):
        collection_name = collection_name_for_subject(subject)
        shard_repository = KnowledgeRepository(
            client=client,
            collection_name=collection_name,
        )
        result = build_knowledge_index(
            corpus_root=root,
            source_files=tuple(groups[subject]),
            corpus_label=subject,
            repository=shard_repository,
            embedding_client=embedding_client,
            embedding_model=embedding_model,
            collection_name=collection_name,
        )
        results.append(result)
        handles.append(
            ShardHandle(
                subject=subject,
                repository=shard_repository,
                fingerprint=result.manifest.fingerprint,
            )
        )

    return ShardRouter(handles), results


def _load_first_shard_manifest(router: ShardRouter) -> IndexManifest:
    """Load one shard manifest for shared embedding-dimension validation."""

    for shard in router.handles:
        slug = shard.subject
        path = PROJECT_ROOT / CHROMA_PERSIST_DIR / f"index_manifest_{slug}.json"
        if path.exists():
            return load_manifest(path)
    raise ManifestError("subject shard manifest is missing")


def build_frozen_evaluation_index(
    *,
    corpus_root: Path,
    repository: KnowledgeRepository,
    embedding_client: EmbeddingClient,
) -> IndexBuildResult:
    """Build the frozen evaluation corpus into the supplied repository."""

    return build_knowledge_index(
        corpus_root=corpus_root,
        source_dir=Path("docs"),
        corpus_label="tests/data/corpus",
        repository=repository,
        embedding_client=embedding_client,
        embedding_model=embedding_client.config.model,
    )


def attach_manifest_summary(summary: dict, manifest: IndexManifest) -> None:
    """Attach stable index traceability fields to an evaluation summary."""

    summary["index_manifest"] = {
        "fingerprint": manifest.fingerprint,
        "corpus": manifest.corpus_root,
        "files": manifest.file_count,
        "chunks": manifest.chunk_count,
        "embedding_model": manifest.embedding_model,
        "embedding_dimensions": manifest.embedding_dimensions,
    }


def validate_existing_index_identity(
    *,
    repository_count: int,
    manifest: IndexManifest,
    embedding_model: str,
) -> None:
    """Reject a persistent index that cannot be identified by its Manifest."""

    if repository_count != manifest.chunk_count:
        raise ManifestError(
            "index chunk count does not match Manifest: "
            f"repository={repository_count}, manifest={manifest.chunk_count}"
        )
    if manifest.collection_name != KNOWLEDGE_COLLECTION_NAME:
        raise ManifestError(
            "index collection does not match configured collection: "
            f"manifest={manifest.collection_name!r}, "
            f"configured={KNOWLEDGE_COLLECTION_NAME!r}"
        )
    if embedding_model != manifest.embedding_model:
        raise ManifestError(
            "query embedding model does not match index embedding model: "
            f"query={embedding_model!r}, manifest={manifest.embedding_model!r}"
        )


def validate_query_embedding_dimensions(
    *,
    query_embedding,
    manifest: IndexManifest,
) -> None:
    """Validate query vector dimensions before any repository operation."""

    try:
        actual_dimensions = len(query_embedding)
    except TypeError as exc:
        raise ManifestError("query embedding must be a vector") from exc

    if actual_dimensions != manifest.embedding_dimensions:
        raise ManifestError(
            "query embedding dimensions do not match index Manifest: "
            f"query={actual_dimensions}, manifest={manifest.embedding_dimensions}"
        )


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


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    """Return P50/P95 query latency in milliseconds."""

    if not values:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
    }


def _rerank_latency_summary(values: list[float]) -> dict[str, float | int]:
    """Return average/P95 rerank latency in milliseconds."""

    if not values:
        return {"count": 0, "average_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "average_ms": round(statistics.fmean(ordered), 3),
        "p95_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3),
    }


def _attach_rerank_case_traces(*, summary, cases, traces, routing: str) -> None:
    """Attach before/after rank evidence without changing core metric semantics."""

    results_by_id = {row["id"]: row for row in summary.get("results", [])}
    for case in cases:
        row = results_by_id.get(case.case_id)
        if row is None:
            continue
        route_subject = case.subject if routing == "routed" else None
        trace = traces.get((case.query, route_subject))
        if trace is None:
            continue
        before_hits = trace["before_hits"]
        after_hits = trace["after_hits"]
        row["before_sources"] = [hit.source for hit in before_hits]
        row["after_sources"] = [hit.source for hit in after_hits]
        row["before_rank"] = _expected_rank(case, before_hits)
        row["after_rank"] = _expected_rank(case, after_hits)
        row["rerank_applied"] = trace["applied"]
        row["rerank_fallback_reason"] = trace["fallback_reason"]


def _expected_rank(case, hits) -> int | None:
    for index, hit in enumerate(hits, 1):
        if hit.source not in case.expected_sources:
            continue
        if case.expected_title_keywords:
            haystack = f"{hit.title_path}\n{hit.content}".lower()
            if not all(keyword.lower() in haystack for keyword in case.expected_title_keywords):
                continue
        return index
    return None


def _run_threshold_sweep(
    cases,
    search,
    top_k: int,
    sweep_values: list[float],
    search_factory=None,
) -> list[dict]:
    """Run metric calculation for several thresholds using cached retrieval hits."""

    rows = []
    for threshold in sweep_values:
        active_search = search_factory(threshold) if search_factory is not None else search
        metrics = evaluate_cases(
            cases=cases,
            search=active_search,
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
    manifest: IndexManifest,
) -> dict:
    """对第一条正例做一次手算 cosine 和 Chroma top-1 对拍。"""

    positive_case = next((case for case in cases if not case.is_negative), None)
    if positive_case is None:
        return {"status": "skipped", "message": "no positive eval case found."}

    query_embedding = embedding_client.embed_texts([positive_case.query])[0]
    validate_query_embedding_dimensions(
        query_embedding=query_embedding,
        manifest=manifest,
    )
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
    print("v0.6 frozen retrieval eval")
    print(f"mode={summary.get('mode', 'vector')} routing={summary.get('routing', 'baseline')}")
    trace = summary["index_manifest"]
    print(
        "manifest={fingerprint} corpus={corpus} files={files} chunks={chunks} "
        "embedding_model={embedding_model} dimensions={embedding_dimensions}".format(
            **trace
        )
    )
    print(
        "cases={total_cases} positives={positive_cases} negatives={negative_cases} "
        "top_k={top_k} threshold={threshold}".format(**metrics)
    )
    print(f"recall@k={metrics['recall_at_k']:.4f}")
    print(f"MRR={metrics['mrr']:.4f}")
    print(f"negative_accuracy={metrics['negative_accuracy']:.4f}")
    print(f"overall_accuracy={metrics['overall_accuracy']:.4f}")
    latency = summary.get("retrieval_latency_ms", summary.get("latency_ms", {}))
    print(
        f"retrieval_latency_ms=P50:{latency.get('p50_ms', 0):.3f} "
        f"P95:{latency.get('p95_ms', 0):.3f}"
    )
    reranking = summary.get("reranking", {})
    rerank_latency = reranking.get("latency_ms", {})
    print(
        "rerank={enabled} candidate_k={candidate_k} provider={provider} model={model} "
        "average_ms={average:.3f} p95_ms={p95:.3f} fallbacks={fallbacks}".format(
            enabled=reranking.get("enabled", False),
            candidate_k=reranking.get("candidate_k"),
            provider=reranking.get("provider"),
            model=reranking.get("model"),
            average=rerank_latency.get("average_ms", 0),
            p95=rerank_latency.get("p95_ms", 0),
            fallbacks=reranking.get("fallback_count", 0),
        )
    )

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
