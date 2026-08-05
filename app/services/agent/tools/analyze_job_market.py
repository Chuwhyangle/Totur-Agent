"""Deterministic market statistics over the committed public JD snapshot."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from app.db.models import PUBLIC_JOB_DESCRIPTIONS_TABLE, PublicJDRecord
from app.repositories.jd_vector_repository import JDVectorRepository
from app.repositories.public_jd_repository import list_public_jds
from app.services.jd_index_state import JDIndexNotReadyError, load_ready_jd_manifest
from app.services.rag_settings import CHROMA_PERSIST_DIR


SUPPORTED_METRICS = frozenset(
    {"direction", "function", "skills", "region", "education", "salary"}
)
SALARY_BUCKETS = (
    ("5k 以下", 0.0, 5.0),
    ("5k-8k", 5.0, 8.0),
    ("8k-12k", 8.0, 12.0),
    ("12k-20k", 12.0, 20.0),
    ("20k 以上", 20.0, float("inf")),
)
DEFAULT_TOP_N = 10
MAX_TOP_N = 20
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = PROJECT_ROOT / CHROMA_PERSIST_DIR / "index_manifest_jd.json"

_repository: JDVectorRepository | None = None


def analyze_job_market(
    metric: str,
    direction: str | None = None,
    relevance: str | None = None,
    education: str | None = None,
    province: str | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    """Aggregate one stable metric after filtering and fingerprint deduplication."""

    normalized_metric = str(metric or "").strip().lower()
    if normalized_metric not in SUPPORTED_METRICS:
        return _error(
            "invalid_arguments",
            "metric must be one of: " + ", ".join(sorted(SUPPORTED_METRICS)),
        )
    try:
        safe_top_n = max(1, min(int(top_n or DEFAULT_TOP_N), MAX_TOP_N))
    except (TypeError, ValueError):
        return _error("invalid_arguments", "top_n must be an integer")
    try:
        _ensure_ready()
    except JDIndexNotReadyError as exc:
        return _error("jd_index_not_ready", f"JD index is not ready: {exc}")

    records = list_public_jds(
        category=direction,
        relevance=relevance,
        education=education,
        province=province,
    )
    unique_records = _deduplicate(records)
    if not unique_records:
        return {
            "ok": True,
            "found": False,
            "metric": normalized_metric,
            "record_count": 0,
            "sample_count": 0,
            "items": [],
            "message": "没有符合筛选条件的 JD 数据。",
        }

    if normalized_metric == "salary":
        return _salary_result(normalized_metric, records, unique_records)

    values = _metric_values(normalized_metric, unique_records)
    if not values:
        return {
            "ok": True,
            "found": False,
            "metric": normalized_metric,
            "record_count": len(records),
            "sample_count": len(unique_records),
            "items": [],
            "message": "当前数据没有该指标的结构化值。",
        }
    counts = Counter(values)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:safe_top_n]
    sample_count = len(unique_records)
    return {
        "ok": True,
        "found": True,
        "metric": normalized_metric,
        "record_count": len(records),
        "sample_count": sample_count,
        "items": [
            {
                "label": label,
                "count": count,
                "percentage": round(count / sample_count * 100, 1),
            }
            for label, count in ranked
        ],
    }


def _ensure_ready() -> None:
    repository = _get_repository()
    records = list_public_jds()
    load_ready_jd_manifest(
        MANIFEST_PATH,
        collection_name=repository.collection_name,
        vector_count=repository.count(),
        vector_snapshot=repository.snapshot_hashes(),
        sqlite_table=PUBLIC_JOB_DESCRIPTIONS_TABLE,
        sqlite_count=len(records),
        sqlite_snapshot={
            record.jd_id: (record.row_sha256, record.parent_sha256)
            for record in records
        },
    )


def _deduplicate(records: list[PublicJDRecord]) -> list[PublicJDRecord]:
    unique: dict[str, PublicJDRecord] = {}
    for record in sorted(records, key=lambda item: item.jd_id):
        unique.setdefault(record.fingerprint, record)
    return list(unique.values())


def _metric_values(metric: str, records: list[PublicJDRecord]) -> list[str]:
    if metric == "skills":
        return [keyword for record in records for keyword in record.keywords]
    field = {
        "direction": "category",
        "function": "function_category",
        "region": "province",
        "education": "education",
    }[metric]
    return [
        value
        for record in records
        if (value := str(getattr(record, field) or "").strip())
    ]


def _salary_result(
    metric: str,
    records: list[PublicJDRecord],
    unique_records: list[PublicJDRecord],
) -> dict[str, Any]:
    lows = [record.salary_min_k for record in unique_records]
    highs = [record.salary_max_k for record in unique_records]
    mids = [(low + high) / 2 for low, high in zip(lows, highs)]
    counts = Counter(_salary_bucket(value) for value in mids)
    sample_count = len(unique_records)
    return {
        "ok": True,
        "found": True,
        "metric": metric,
        "record_count": len(records),
        "sample_count": sample_count,
        "items": [
            {
                "label": label,
                "count": counts.get(label, 0),
                "percentage": round(counts.get(label, 0) / sample_count * 100, 1),
            }
            for label, _low, _high in SALARY_BUCKETS
        ],
        "statistics": {
            "median_min_k": round(float(median(lows)), 2),
            "median_max_k": round(float(median(highs)), 2),
            "median_mid_k": round(float(median(mids)), 2),
        },
    }


def _salary_bucket(value: float) -> str:
    for label, low, high in SALARY_BUCKETS:
        if low <= value < high:
            return label
    return "20k 以上"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message}


def _get_repository() -> JDVectorRepository:
    global _repository
    if _repository is None:
        _repository = JDVectorRepository()
    return _repository
