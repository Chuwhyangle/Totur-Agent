import sqlite3

from app.db import database
from app.db.models import PUBLIC_JOB_DESCRIPTIONS_TABLE, PublicJDRecord
from app.repositories.public_jd_repository import (
    count_public_jds,
    list_public_jds,
    sync_public_jds,
)


def _record(
    jd_id: str = "agent_dev:abc123def456",
    *,
    category: str = "agent_dev",
    fingerprint: str = "abc123def456",
    title: str = "Agent工程师",
    education: str = "本科及以上",
    province: str = "湖北省",
    salary_min_k: float = 16.0,
    salary_max_k: float = 20.0,
) -> PublicJDRecord:
    return PublicJDRecord(
        jd_id=jd_id,
        fingerprint=fingerprint,
        category=category,
        source_path=f"corpus/JD/{category}/jobs/example.md",
        source_url="https://example.com/jobs/1",
        title=title,
        company="示例公司",
        salary_raw=f"{salary_min_k:g}k-{salary_max_k:g}k",
        salary_min_k=salary_min_k,
        salary_max_k=salary_max_k,
        education=education,
        recruitment_count="2人",
        major="计算机相关",
        region="湖北省武汉市",
        province=province,
        source_updated_at="08-05 10:00",
        industry="软件和信息技术服务业",
        company_type="民营企业",
        company_size="100-499人",
        relevance="直接相关",
        relevance_score=67,
        function_category="Agent/AI 开发",
        keywords=("Python", "Agent", "RAG"),
        duplicate_count=1,
        row_sha256="a" * 64,
        parent_sha256="b" * 64,
    )


def _use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "public-jds.db")


def test_initialize_database_creates_public_job_descriptions_table(
    monkeypatch, tmp_path
):
    _use_temp_database(monkeypatch, tmp_path)

    database.initialize_database()

    connection = sqlite3.connect(database.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(
                f"PRAGMA table_info({PUBLIC_JOB_DESCRIPTIONS_TABLE})"
            )
        }
    finally:
        connection.close()

    assert {
        "jd_id",
        "fingerprint",
        "category",
        "source_path",
        "salary_min_k",
        "salary_max_k",
        "province",
        "keywords_json",
        "row_sha256",
        "parent_sha256",
    }.issubset(columns)


def test_sync_public_jds_upserts_and_deletes_in_one_snapshot(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    first = _record()
    second = _record(
        "marketing:def456abc123",
        category="marketing",
        fingerprint="def456abc123",
        title="新媒体运营",
        education="专科及以上",
        province="上海",
        salary_min_k=6.0,
        salary_max_k=10.0,
    )

    assert sync_public_jds([first, second], [], full_rebuild=True) == 2
    updated = _record(title="高级Agent工程师")
    assert sync_public_jds([updated], [second.jd_id]) == 1

    records = list_public_jds()
    assert count_public_jds() == 1
    assert [record.jd_id for record in records] == [first.jd_id]
    assert records[0].title == "高级Agent工程师"
    assert records[0].keywords == ("Python", "Agent", "RAG")


def test_list_public_jds_applies_core_filters(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    records = [
        _record(),
        _record(
            "marketing:def456abc123",
            category="marketing",
            fingerprint="def456abc123",
            title="新媒体运营",
            education="专科及以上",
            province="上海",
            salary_min_k=6.0,
            salary_max_k=10.0,
        ),
    ]
    sync_public_jds(records, [], full_rebuild=True)

    filtered = list_public_jds(
        category="agent_dev",
        education="本科及以上",
        province="湖北省",
        salary_floor_k=15,
        salary_ceiling_k=25,
    )

    assert [record.jd_id for record in filtered] == [records[0].jd_id]
