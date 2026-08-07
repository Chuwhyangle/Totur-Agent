"""SQLite access for the imported public JD corpus."""

from __future__ import annotations

import json
from typing import Iterable

from app.db.database import get_connection, initialize_database
from app.db.models import PUBLIC_JOB_DESCRIPTIONS_TABLE, PublicJDRecord


_COLUMNS = (
    "jd_id",
    "fingerprint",
    "category",
    "source_path",
    "source_url",
    "title",
    "company",
    "salary_raw",
    "salary_min_k",
    "salary_max_k",
    "education",
    "recruitment_count",
    "major",
    "region",
    "province",
    "source_updated_at",
    "industry",
    "company_type",
    "company_size",
    "relevance",
    "relevance_score",
    "function_category",
    "keywords_json",
    "duplicate_count",
    "row_sha256",
    "parent_sha256",
)


def sync_public_jds(
    records: Iterable[PublicJDRecord],
    delete_ids: Iterable[str],
    *,
    full_rebuild: bool = False,
) -> int:
    """Apply one idempotent SQLite snapshot mutation in a transaction."""

    initialize_database()
    normalized_records = tuple(records)
    normalized_delete_ids = tuple(dict.fromkeys(delete_ids))
    placeholders = ", ".join("?" for _ in _COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}" for column in _COLUMNS if column != "jd_id"
    )
    sql = f"""
    INSERT INTO {PUBLIC_JOB_DESCRIPTIONS_TABLE} ({', '.join(_COLUMNS)})
    VALUES ({placeholders})
    ON CONFLICT(jd_id) DO UPDATE SET {updates}
    """
    connection = get_connection()
    try:
        if full_rebuild:
            connection.execute(f"DELETE FROM {PUBLIC_JOB_DESCRIPTIONS_TABLE}")
        elif normalized_delete_ids:
            delete_placeholders = ", ".join("?" for _ in normalized_delete_ids)
            connection.execute(
                f"DELETE FROM {PUBLIC_JOB_DESCRIPTIONS_TABLE} "
                f"WHERE jd_id IN ({delete_placeholders})",
                normalized_delete_ids,
            )
        if normalized_records:
            connection.executemany(sql, [_record_values(record) for record in normalized_records])
        connection.commit()
        row = connection.execute(
            f"SELECT COUNT(*) AS total FROM {PUBLIC_JOB_DESCRIPTIONS_TABLE}"
        ).fetchone()
        return int(row["total"])
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def count_public_jds() -> int:
    initialize_database()
    connection = get_connection()
    try:
        row = connection.execute(
            f"SELECT COUNT(*) AS total FROM {PUBLIC_JOB_DESCRIPTIONS_TABLE}"
        ).fetchone()
        return int(row["total"])
    finally:
        connection.close()


def list_public_jds(
    *,
    category: str | None = None,
    relevance: str | None = None,
    education: str | None = None,
    province: str | None = None,
    salary_floor_k: float | None = None,
    salary_ceiling_k: float | None = None,
) -> list[PublicJDRecord]:
    """List structured JDs with deterministic exact filters."""

    initialize_database()
    clauses: list[str] = []
    parameters: list[object] = []
    for column, value in (
        ("category", category),
        ("relevance", relevance),
        ("education", education),
        ("province", province),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            parameters.append(value)
    if salary_floor_k is not None:
        clauses.append("salary_min_k >= ?")
        parameters.append(float(salary_floor_k))
    if salary_ceiling_k is not None:
        clauses.append("salary_max_k <= ?")
        parameters.append(float(salary_ceiling_k))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = get_connection()
    try:
        rows = connection.execute(
            f"SELECT {', '.join(_COLUMNS)} "
            f"FROM {PUBLIC_JOB_DESCRIPTIONS_TABLE} {where} ORDER BY jd_id",
            parameters,
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def _record_values(record: PublicJDRecord) -> tuple[object, ...]:
    return (
        record.jd_id,
        record.fingerprint,
        record.category,
        record.source_path,
        record.source_url,
        record.title,
        record.company,
        record.salary_raw,
        record.salary_min_k,
        record.salary_max_k,
        record.education,
        record.recruitment_count,
        record.major,
        record.region,
        record.province,
        record.source_updated_at,
        record.industry,
        record.company_type,
        record.company_size,
        record.relevance,
        record.relevance_score,
        record.function_category,
        json.dumps(record.keywords, ensure_ascii=False),
        record.duplicate_count,
        record.row_sha256,
        record.parent_sha256,
    )


def _record_from_row(row) -> PublicJDRecord:
    return PublicJDRecord(
        jd_id=row["jd_id"],
        fingerprint=row["fingerprint"],
        category=row["category"],
        source_path=row["source_path"],
        source_url=row["source_url"],
        title=row["title"],
        company=row["company"],
        salary_raw=row["salary_raw"],
        salary_min_k=float(row["salary_min_k"]),
        salary_max_k=float(row["salary_max_k"]),
        education=row["education"],
        recruitment_count=row["recruitment_count"],
        major=row["major"],
        region=row["region"],
        province=row["province"],
        source_updated_at=row["source_updated_at"],
        industry=row["industry"],
        company_type=row["company_type"],
        company_size=row["company_size"],
        relevance=row["relevance"],
        relevance_score=int(row["relevance_score"]),
        function_category=row["function_category"],
        keywords=tuple(json.loads(row["keywords_json"])),
        duplicate_count=int(row["duplicate_count"]),
        row_sha256=row["row_sha256"],
        parent_sha256=row["parent_sha256"],
    )
