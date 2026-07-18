"""Run reproducible retrieval evaluation against a frozen Chroma index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from chromadb.config import Settings
from chromadb.errors import ChromaError

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.config import load_embedding_config
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.hybrid_retriever import hybrid_search
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
    RAG_TOP_K,
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
        config = load_embedding_config()
        embedding_client = EmbeddingClient(config=config)

        if args.use_existing_index:
            repository = KnowledgeRepository()
            manifest = load_manifest(DEFAULT_MANIFEST_PATH)
            validate_existing_index_identity(
                repository_count=repository.count(),
                manifest=manifest,
                embedding_model=config.model,
            )
        else:
            repository = KnowledgeRepository(
                client=chromadb.EphemeralClient(
                    settings=Settings(anonymized_telemetry=False)
                )
            )
            result = build_frozen_evaluation_index(
                corpus_root=args.corpus_root,
                repository=repository,
                embedding_client=embedding_client,
            )
            manifest = result.manifest

        cached_hits = {}

        def search(query: str, top_k: int):
            if query in cached_hits:
                return cached_hits[query][:top_k]

            query_embedding = embedding_client.embed_texts([query])[0]
            validate_query_embedding_dimensions(
                query_embedding=query_embedding,
                manifest=manifest,
            )
            if args.mode == "hybrid":
                hits = hybrid_search(
                    repository=repository,
                    query=query,
                    query_embedding=query_embedding,
                    top_k=args.top_k,
                    fingerprint=manifest.fingerprint,
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
        attach_manifest_summary(summary, manifest)
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
    print("v0.5 frozen retrieval eval")
    print(f"mode={summary.get('mode', 'vector')}")
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
