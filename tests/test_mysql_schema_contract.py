"""MySQL schema 契约测试（数据库重构文档 B1/B3 验收）。

Opt-in 集成测试：需要可用的 MySQL（先 `docker compose up -d mysql` 并
`python scripts/init_databases.py`）。MySQL 不可达时整模块 skip。

运行：python -m pytest tests/test_mysql_schema_contract.py -m mysql -v
"""

import os

import pymysql
import pytest
from dotenv import load_dotenv


load_dotenv()

pytestmark = pytest.mark.mysql


def _connect(database: str = "tutor_agent") -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("TRACE_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("TRACE_DB_PORT", "3306")),
        user="app",
        password=os.getenv("MYSQL_APP_PASSWORD", ""),
        database=database,
    )


def _mysql_available() -> bool:
    try:
        connection = _connect()
        connection.close()
        return True
    except pymysql.MySQLError:
        return False


@pytest.fixture(autouse=True)
def require_mysql():
    if not _mysql_available():
        pytest.skip(
            "MySQL 不可用：先 docker compose up -d mysql 并 "
            "python scripts/init_databases.py"
        )


def _fetch_all(connection: pymysql.Connection, sql: str):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def test_mysql_server_timezone_and_sql_mode_are_utc():
    """B1 验收：服务端时区 UTC、严格模式开启。"""

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT @@global.time_zone, @@session.time_zone, "
                "@@log_timestamps, @@sql_mode"
            )
            global_tz, session_tz, log_ts, sql_mode = cursor.fetchone()
    finally:
        connection.close()

    assert global_tz == "+00:00"
    assert session_tz == "+00:00"
    assert log_ts == "UTC"
    assert "STRICT_TRANS_TABLES" in sql_mode


def test_business_schema_has_workspace_foundation_tables():
    """B3 验收：基础业务表和 Workspace 契约表全部存在。"""

    connection = _connect()
    try:
        rows = _fetch_all(
            connection,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'tutor_agent'",
        )
        tables = {row[0] for row in rows}
    finally:
        connection.close()

    assert tables == {
        "alembic_version",
        "chat_sessions",
        "conversations",
        "session_summaries",
        "interview_jds",
        "public_job_descriptions",
        "documents",
        "journal_entries",
        "workspaces",
        "workspace_assets",
        "tasks",
        "task_steps",
        "task_asset_refs",
        "artifacts",
        "artifact_sources",
    }


def test_tutor_agent_ops_database_exists():
    """B3 建库：trace 库 tutor_agent_ops 存在。"""

    connection = _connect()
    try:
        rows = _fetch_all(
            connection,
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = 'tutor_agent_ops'",
        )
    finally:
        connection.close()

    assert len(rows) == 1


def test_column_collations_follow_d7():
    """B3 验收：collation 分配与 D7 完全一致。

    人类文本 → utf8mb4_0900_ai_ci；标识符/路径 → utf8mb4_0900_bin；
    纯 hex 与 UUID → ascii_bin。
    """

    connection = _connect()
    try:
        rows = _fetch_all(
            connection,
            "SELECT table_name, column_name, collation_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'tutor_agent' "
            "AND collation_name IS NOT NULL",
        )
    finally:
        connection.close()

    collations = {
        (table, column): collation for table, column, collation in rows
    }

    # 人类文本列（表默认 utf8mb4_0900_ai_ci 或显式声明）
    ai_ci_columns = {
        ("chat_sessions", "title"),
        ("conversations", "message"),
        ("conversations", "reply_json"),
        ("session_summaries", "summary_text"),
        ("interview_jds", "title"),
        ("interview_jds", "raw_text"),
        ("public_job_descriptions", "title"),
        ("public_job_descriptions", "company"),
        ("public_job_descriptions", "salary_raw"),
        ("public_job_descriptions", "education"),
        ("public_job_descriptions", "recruitment_count"),
        ("public_job_descriptions", "major"),
        ("public_job_descriptions", "region"),
        ("public_job_descriptions", "province"),
        ("public_job_descriptions", "source_updated_at"),
        ("public_job_descriptions", "industry"),
        ("public_job_descriptions", "company_type"),
        ("public_job_descriptions", "company_size"),
        ("public_job_descriptions", "function_category"),
        ("documents", "original_filename"),
        ("documents", "error_message"),
        ("journal_entries", "title"),
        ("journal_entries", "content"),
        ("journal_entries", "tags"),
        ("workspaces", "name"),
        ("workspaces", "description"),
        ("workspace_assets", "original_filename"),
        ("workspace_assets", "error_message"),
        ("tasks", "goal"),
        ("task_steps", "input_summary"),
        ("task_steps", "output_summary"),
        ("artifacts", "title"),
    }
    # 标识符与路径列
    bin_columns = {
        ("chat_sessions", "user_id"),
        ("chat_sessions", "persona_id"),
        ("chat_sessions", "subject"),
        ("conversations", "user_id"),
        ("interview_jds", "user_id"),
        ("interview_jds", "role_family"),
        ("interview_jds", "seniority"),
        ("public_job_descriptions", "jd_id"),
        ("public_job_descriptions", "fingerprint"),
        ("public_job_descriptions", "category"),
        ("public_job_descriptions", "source_path"),
        ("public_job_descriptions", "source_url"),
        ("public_job_descriptions", "relevance"),
        ("documents", "scope"),
        ("documents", "user_id"),
        ("documents", "mime_type"),
        ("documents", "storage_path"),
        ("documents", "parsed_path"),
        ("documents", "status"),
        ("documents", "parser_name"),
        ("documents", "parser_version"),
        ("documents", "error_code"),
        ("journal_entries", "persona_id"),
        ("workspaces", "user_id"),
        ("workspaces", "status"),
        ("workspace_assets", "media_type"),
        ("workspace_assets", "storage_key"),
        ("workspace_assets", "parsed_storage_key"),
        ("workspace_assets", "status"),
        ("workspace_assets", "parser_name"),
        ("workspace_assets", "parser_version"),
        ("workspace_assets", "error_code"),
        ("tasks", "status"),
        ("tasks", "error_code"),
        ("task_steps", "tool_call_id"),
        ("task_steps", "step_type"),
        ("task_steps", "tool_name"),
        ("task_steps", "status"),
        ("task_steps", "error_code"),
        ("artifacts", "media_type"),
        ("artifacts", "storage_key"),
        ("artifacts", "creation_key"),
        ("artifacts", "status"),
        ("artifacts", "error_code"),
    }
    # 纯 hex 与 UUID（D7）
    ascii_bin_columns = {
        ("documents", "id"),
        ("public_job_descriptions", "source_path_sha256"),
        ("public_job_descriptions", "row_sha256"),
        ("public_job_descriptions", "parent_sha256"),
        ("documents", "content_hash"),
        ("conversations", "reply_format"),
        ("chat_sessions", "workspace_id"),
        ("workspaces", "id"),
        ("workspace_assets", "id"),
        ("workspace_assets", "workspace_id"),
        ("workspace_assets", "content_hash"),
        ("workspace_assets", "dedupe_key"),
        ("tasks", "id"),
        ("tasks", "workspace_id"),
        ("tasks", "trace_id"),
        ("task_steps", "task_id"),
        ("task_asset_refs", "task_id"),
        ("task_asset_refs", "asset_id"),
        ("artifacts", "id"),
        ("artifacts", "workspace_id"),
        ("artifacts", "task_id"),
        ("artifacts", "artifact_series_id"),
        ("artifacts", "supersedes_artifact_id"),
        ("artifacts", "content_hash"),
        ("artifact_sources", "artifact_id"),
        ("artifact_sources", "asset_id"),
    }

    for column in ai_ci_columns:
        assert collations.get(column) == "utf8mb4_0900_ai_ci", column
    for column in bin_columns:
        assert collations.get(column) == "utf8mb4_0900_bin", column
    for column in ascii_bin_columns:
        assert collations.get(column) == "ascii_bin", column


def test_check_constraints_reject_invalid_rows():
    """B3 验收：跨列 CHECK（scope shape / FAILED needs error）生效。"""

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            # ATTACHMENT 必须 user_id/session_id/expires_at 齐全
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(
                    "INSERT INTO documents ("
                    "id, scope, original_filename, mime_type, size_bytes, "
                    "storage_path, status, created_at, updated_at"
                    ") VALUES (%s, 'ATTACHMENT', 'a.pdf', 'application/pdf', "
                    "10, 'keys/a.pdf', 'UPLOADED', NOW(6), NOW(6))",
                    ("00000000-0000-4000-8000-000000000001",),
                )
            # FAILED 状态必须带 error_code
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(
                    "INSERT INTO documents ("
                    "id, scope, user_id, session_id, original_filename, "
                    "mime_type, size_bytes, storage_path, status, "
                    "created_at, updated_at, expires_at"
                    ") VALUES (%s, 'ATTACHMENT', 'u', 1, 'a.pdf', "
                    "'application/pdf', 10, 'keys/a.pdf', 'FAILED', "
                    "NOW(6), NOW(6), DATE_ADD(NOW(6), INTERVAL 1 DAY))",
                    ("00000000-0000-4000-8000-000000000002",),
                )
        connection.rollback()
    finally:
        connection.close()


def test_invalid_json_is_rejected():
    """B3 验收：JSON 列拒绝非法 JSON。"""

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(
                    "INSERT INTO interview_jds ("
                    "user_id, title, target_graduation_years_json, raw_text, "
                    "responsibilities_json, must_have_json, core_skills_json, "
                    "preferred_skills_json, bonus_skills_json, keywords_json, "
                    "interview_focus_json, created_at, updated_at"
                    ") VALUES ('u', 't', 'not-json', 'raw', '[]', '[]', '[]', "
                    "'[]', '[]', '[]', '[]', NOW(6), NOW(6))"
                )
        connection.rollback()
    finally:
        connection.close()


def test_foreign_keys_reject_orphan_conversation():
    """B3 验收：conversations.session_id 外键拒绝孤儿行。"""

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(
                    "INSERT INTO conversations ("
                    "session_id, user_id, message, reply_json, created_at"
                    ") VALUES (999999, 'u', 'hi', '{}', NOW(6))"
                )
        connection.rollback()
    finally:
        connection.close()
