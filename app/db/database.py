"""SQLite 连接和数据库表初始化。

A1 后仅保留 schema 初始化职责；连接统一来自 app.db.engine。
"""

import sqlite3

from sqlalchemy import text

from app.db.engine import get_engine
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DEFAULT_SESSION_TITLE,
    DOCUMENTS_TABLE,
    INTERVIEW_JDS_TABLE,
    JOURNAL_ENTRIES_TABLE,
    PUBLIC_JOB_DESCRIPTIONS_TABLE,
    SESSION_SUMMARIES_TABLE,
)


def initialize_database() -> None:
    """创建数据库表，并处理旧数据库的轻量迁移。"""

    create_sessions_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {CHAT_SESSIONS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        persona_id TEXT NOT NULL DEFAULT 'tutor',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """

    create_conversations_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {CONVERSATIONS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER REFERENCES {CHAT_SESSIONS_TABLE}(id),
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        reply_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """
    create_session_summaries_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {SESSION_SUMMARIES_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL UNIQUE
            REFERENCES {CHAT_SESSIONS_TABLE}(id) ON DELETE CASCADE,
        summary_text TEXT NOT NULL,
        last_conversation_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """
    create_interview_jds_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {INTERVIEW_JDS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        role_family TEXT,
        seniority TEXT,
        target_graduation_years_json TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        responsibilities_json TEXT NOT NULL,
        must_have_json TEXT NOT NULL,
        core_skills_json TEXT NOT NULL,
        preferred_skills_json TEXT NOT NULL,
        bonus_skills_json TEXT NOT NULL,
        keywords_json TEXT NOT NULL,
        interview_focus_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """
    create_documents_table_sql = _create_documents_table_sql(DOCUMENTS_TABLE)
    create_public_job_descriptions_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {PUBLIC_JOB_DESCRIPTIONS_TABLE} (
        jd_id TEXT PRIMARY KEY,
        fingerprint TEXT NOT NULL,
        category TEXT NOT NULL,
        source_path TEXT NOT NULL UNIQUE,
        source_url TEXT NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        salary_raw TEXT NOT NULL,
        salary_min_k REAL NOT NULL,
        salary_max_k REAL NOT NULL,
        education TEXT NOT NULL,
        recruitment_count TEXT NOT NULL,
        major TEXT NOT NULL,
        region TEXT NOT NULL,
        province TEXT NOT NULL,
        source_updated_at TEXT NOT NULL,
        industry TEXT NOT NULL,
        company_type TEXT NOT NULL,
        company_size TEXT NOT NULL,
        relevance TEXT NOT NULL,
        relevance_score INTEGER NOT NULL,
        function_category TEXT NOT NULL,
        keywords_json TEXT NOT NULL,
        duplicate_count INTEGER NOT NULL CHECK (duplicate_count >= 1),
        row_sha256 TEXT NOT NULL,
        parent_sha256 TEXT NOT NULL
    );
    """
    create_journal_entries_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {JOURNAL_ENTRIES_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER REFERENCES {CHAT_SESSIONS_TABLE}(id) ON DELETE SET NULL,
        persona_id TEXT NOT NULL DEFAULT 'journal',
        title TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '',
        entry_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """
    create_sessions_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
    ON {CHAT_SESSIONS_TABLE} (user_id, updated_at DESC, id DESC);
    """
    create_conversations_session_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_conversations_session_id
    ON {CONVERSATIONS_TABLE} (session_id, id DESC);
    """
    create_conversations_user_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON {CONVERSATIONS_TABLE} (user_id, id DESC);
    """
    create_session_summaries_last_conversation_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_session_summaries_last_conversation
    ON {SESSION_SUMMARIES_TABLE} (last_conversation_id);
    """
    create_interview_jds_user_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_interview_jds_user_updated
    ON {INTERVIEW_JDS_TABLE} (user_id, updated_at DESC, id DESC);
    """
    create_public_jds_filter_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_public_jds_filters
    ON {PUBLIC_JOB_DESCRIPTIONS_TABLE}
        (category, relevance, education, province, salary_min_k, salary_max_k);
    """
    create_public_jds_fingerprint_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_public_jds_fingerprint
    ON {PUBLIC_JOB_DESCRIPTIONS_TABLE} (fingerprint);
    """
    create_documents_user_session_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_documents_user_session
    ON {DOCUMENTS_TABLE} (user_id, session_id);
    """
    create_documents_status_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_documents_status
    ON {DOCUMENTS_TABLE} (status);
    """
    create_documents_expires_at_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_documents_expires_at
    ON {DOCUMENTS_TABLE} (expires_at);
    """
    create_journal_entries_date_index_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_journal_entries_entry_date
    ON {JOURNAL_ENTRIES_TABLE} (entry_date DESC);
    """

    with get_engine().begin() as connection:
        connection.execute(text(create_sessions_table_sql))
        connection.execute(text(create_conversations_table_sql))
        # 旧版 chat_sessions 表没有 persona_id，这里会自动补上。
        _ensure_chat_sessions_persona_id_column(connection)
        _ensure_chat_sessions_subject_column(connection)
        # 每个会话只保留一条滚动摘要，后续由 repository 负责更新它。
        connection.execute(text(create_session_summaries_table_sql))
        # JD 是用户提供的目标岗位资料，先持久化，再让后续工具检索它。
        connection.execute(text(create_interview_jds_table_sql))
        # Public corpus JDs are synchronized offline for search filters and analytics.
        connection.execute(text(create_public_job_descriptions_table_sql))
        # Document rows retain cleanup paths until lifecycle cleanup is complete.
        connection.execute(text(create_documents_table_sql))
        _ensure_documents_schema(connection)
        # Journal entries for daily learning logs.
        connection.execute(text(create_journal_entries_table_sql))
        # 旧版 conversations 表没有 session_id，这里会自动补上。
        _ensure_conversations_session_id_column(connection)
        # 把旧数据按 user_id 归入一个“默认会话”。
        _migrate_existing_conversations_to_default_sessions(connection)
        connection.execute(text(create_sessions_index_sql))
        connection.execute(text(create_conversations_session_index_sql))
        connection.execute(text(create_conversations_user_index_sql))
        connection.execute(text(create_session_summaries_last_conversation_index_sql))
        connection.execute(text(create_interview_jds_user_index_sql))
        connection.execute(text(create_public_jds_filter_index_sql))
        connection.execute(text(create_public_jds_fingerprint_index_sql))
        connection.execute(text(create_documents_user_session_index_sql))
        connection.execute(text(create_documents_status_index_sql))
        connection.execute(text(create_documents_expires_at_index_sql))
        connection.execute(text(create_journal_entries_date_index_sql))


def _create_documents_table_sql(table_name: str) -> str:
    """Build the documents table SQL for first creation and FK migration."""

    return f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL
            CHECK (scope IN ('INTERNAL', 'PRIVATE', 'ATTACHMENT')),
        user_id TEXT,
        session_id INTEGER
            REFERENCES {CHAT_SESSIONS_TABLE}(id) ON DELETE RESTRICT,
        message_id INTEGER,
        original_filename TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        storage_path TEXT NOT NULL,
        parsed_path TEXT,
        content_hash TEXT,
        status TEXT NOT NULL CHECK (status IN (
            'UPLOADED',
            'PARSING',
            'INDEXING',
            'READY',
            'PARTIAL',
            'FAILED',
            'DELETING',
            'DELETED'
        )),
        parser_name TEXT,
        parser_version TEXT,
        page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
        error_code TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        expires_at TEXT,
        CHECK (
            (
                scope = 'ATTACHMENT'
                AND user_id IS NOT NULL
                AND session_id IS NOT NULL
                AND expires_at IS NOT NULL
            )
            OR (
                scope = 'PRIVATE'
                AND user_id IS NOT NULL
                AND session_id IS NULL
            )
            OR (
                scope = 'INTERNAL'
                AND user_id IS NULL
                AND session_id IS NULL
                AND expires_at IS NULL
            )
        ),
        CHECK (
            status <> 'FAILED'
            OR (error_code IS NOT NULL AND length(trim(error_code)) > 0)
        )
    );
    """


def _ensure_documents_schema(connection: sqlite3.Connection) -> None:
    """Idempotently add INDEXING and retain cleanup-safe session ownership."""

    table_row = connection.execute(
        text(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"
        ),
        {"name": DOCUMENTS_TABLE},
    ).mappings().fetchone()
    if table_row is None:
        return

    table_sql = str(table_row["sql"] or "").upper()
    supports_indexing = "'INDEXING'" in table_sql
    foreign_keys = connection.execute(
        text(f"PRAGMA foreign_key_list({DOCUMENTS_TABLE})")
    ).mappings().fetchall()
    session_foreign_key = next(
        (
            row
            for row in foreign_keys
            if row["table"] == CHAT_SESSIONS_TABLE
            and row["from"] == "session_id"
        ),
        None,
    )
    restricts_session_delete = (
        session_foreign_key is not None
        and session_foreign_key["on_delete"].upper() == "RESTRICT"
    )
    if supports_indexing and restricts_session_delete:
        return

    temporary_table = f"{DOCUMENTS_TABLE}_schema_migration"
    columns = """
        id,
        scope,
        user_id,
        session_id,
        message_id,
        original_filename,
        mime_type,
        size_bytes,
        storage_path,
        parsed_path,
        content_hash,
        status,
        parser_name,
        parser_version,
        page_count,
        error_code,
        error_message,
        created_at,
        updated_at,
        expires_at
    """
    connection.execute(text(f"DROP TABLE IF EXISTS {temporary_table}"))
    connection.execute(text(_create_documents_table_sql(temporary_table)))

    if supports_indexing:
        connection.execute(
            text(
                f"""
                INSERT INTO {temporary_table} ({columns})
                SELECT {columns}
                FROM {DOCUMENTS_TABLE}
                """
            )
        )
    else:
        # READY/PARTIAL rows created before attachment vector indexing existed
        # must not remain retrievable after the schema gains INDEXING.
        connection.execute(
            text(
                f"""
                INSERT INTO {temporary_table} ({columns})
                SELECT
                    id,
                scope,
                user_id,
                session_id,
                message_id,
                original_filename,
                mime_type,
                size_bytes,
                storage_path,
                parsed_path,
                content_hash,
                CASE
                    WHEN status IN ('READY', 'PARTIAL') THEN 'FAILED'
                    ELSE status
                END,
                parser_name,
                parser_version,
                page_count,
                CASE
                    WHEN status IN ('READY', 'PARTIAL') THEN 'REINDEX_REQUIRED'
                    ELSE error_code
                END,
                CASE
                    WHEN status IN ('READY', 'PARTIAL')
                        THEN 'Existing parsed attachment requires indexing'
                    ELSE error_message
                END,
                created_at,
                updated_at,
                expires_at
            FROM {DOCUMENTS_TABLE}
            """
            )
        )

    connection.execute(text(f"DROP TABLE {DOCUMENTS_TABLE}"))
    connection.execute(
        text(f"ALTER TABLE {temporary_table} RENAME TO {DOCUMENTS_TABLE}")
    )


def _ensure_chat_sessions_subject_column(connection: sqlite3.Connection) -> None:
    """Add the nullable subject column to legacy chat_sessions tables."""

    columns = {
        row["name"]
        for row in connection.execute(
            text(f"PRAGMA table_info({CHAT_SESSIONS_TABLE})")
        ).mappings()
    }
    if "subject" not in columns:
        connection.execute(
            text(f"ALTER TABLE {CHAT_SESSIONS_TABLE} ADD COLUMN subject TEXT")
        )


def _ensure_conversations_session_id_column(connection: sqlite3.Connection) -> None:
    """给旧版 conversations 表补上 session_id 字段。"""

    columns = {
        row["name"]
        for row in connection.execute(
            text(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
        ).mappings()
    }

    if "session_id" not in columns:
        connection.execute(
            text(
                f"ALTER TABLE {CONVERSATIONS_TABLE} ADD COLUMN session_id INTEGER"
            )
        )


def _ensure_chat_sessions_persona_id_column(connection: sqlite3.Connection) -> None:
    """给旧版 chat_sessions 表补上 persona_id 字段。"""

    columns = {
        row["name"]
        for row in connection.execute(
            text(f"PRAGMA table_info({CHAT_SESSIONS_TABLE})")
        ).mappings()
    }

    if "persona_id" not in columns:
        connection.execute(
            text(
                f"""
                ALTER TABLE {CHAT_SESSIONS_TABLE}
                ADD COLUMN persona_id TEXT NOT NULL DEFAULT 'tutor'
                """
            )
        )


def _migrate_existing_conversations_to_default_sessions(
    connection: sqlite3.Connection,
) -> None:
    """把旧的用户历史记录迁移到每个用户自己的默认会话。"""

    users_with_old_rows = connection.execute(
        text(
            f"""
            SELECT
                user_id,
                MIN(created_at) AS first_created_at,
                MAX(created_at) AS last_created_at
            FROM {CONVERSATIONS_TABLE}
            WHERE session_id IS NULL
            GROUP BY user_id
            """
        )
    ).mappings().fetchall()

    for row in users_with_old_rows:
        user_id = row["user_id"]
        first_created_at = row["first_created_at"]
        last_created_at = row["last_created_at"]
        # 每个 user_id 只创建或复用一个默认会话。
        session_id = _get_or_create_default_session_id(
            connection=connection,
            user_id=user_id,
            created_at=first_created_at,
            updated_at=last_created_at,
        )

        connection.execute(
            text(
                f"""
                UPDATE {CONVERSATIONS_TABLE}
                SET session_id = :session_id
                WHERE user_id = :user_id AND session_id IS NULL
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )


def _get_or_create_default_session_id(
    connection: sqlite3.Connection,
    user_id: str,
    created_at: str,
    updated_at: str,
) -> int:
    """获取某个用户的默认会话 id；没有就创建。"""

    row = connection.execute(
        text(
            f"""
            SELECT id
            FROM {CHAT_SESSIONS_TABLE}
            WHERE user_id = :user_id AND title = :title
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"user_id": user_id, "title": DEFAULT_SESSION_TITLE},
    ).mappings().fetchone()

    if row is not None:
        # 如果默认会话已存在，就把更新时间推进到旧数据的最新时间。
        connection.execute(
            text(
                f"""
                UPDATE {CHAT_SESSIONS_TABLE}
                SET updated_at = MAX(updated_at, :updated_at)
                WHERE id = :id
                """
            ),
            {"updated_at": updated_at, "id": row["id"]},
        )
        return int(row["id"])

    cursor = connection.execute(
        text(
            f"""
            INSERT INTO {CHAT_SESSIONS_TABLE}
                (user_id, title, persona_id, created_at, updated_at)
            VALUES (:user_id, :title, :persona_id, :created_at, :updated_at)
            """
        ),
        {
            "user_id": user_id,
            "title": DEFAULT_SESSION_TITLE,
            "persona_id": "tutor",
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )
    new_id = cursor.lastrowid

    if new_id is None:
        raise RuntimeError("创建默认会话失败：没有拿到新记录 id")

    return new_id
