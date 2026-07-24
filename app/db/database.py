"""SQLite 连接和数据库表初始化。"""

from pathlib import Path
import sqlite3

from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DEFAULT_SESSION_TITLE,
    DOCUMENTS_TABLE,
    INTERVIEW_JDS_TABLE,
    SESSION_SUMMARIES_TABLE,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "tutor_agent.db"


def get_connection() -> sqlite3.Connection:
    """创建一个 SQLite 数据库连接。"""

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row
    # 开启外键检查，让 conversations.session_id 能关联到 chat_sessions.id。
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


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
    create_documents_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {DOCUMENTS_TABLE} (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL
            CHECK (scope IN ('INTERNAL', 'PRIVATE', 'ATTACHMENT')),
        user_id TEXT,
        session_id INTEGER
            REFERENCES {CHAT_SESSIONS_TABLE}(id) ON DELETE CASCADE,
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

    connection = get_connection()
    try:
        connection.execute(create_sessions_table_sql)
        connection.execute(create_conversations_table_sql)
        # 旧版 chat_sessions 表没有 persona_id，这里会自动补上。
        _ensure_chat_sessions_persona_id_column(connection)
        _ensure_chat_sessions_subject_column(connection)
        # 每个会话只保留一条滚动摘要，后续由 repository 负责更新它。
        connection.execute(create_session_summaries_table_sql)
        # JD 是用户提供的目标岗位资料，先持久化，再让后续工具检索它。
        connection.execute(create_interview_jds_table_sql)
        # Store document metadata only; session deletion cascades records.
        connection.execute(create_documents_table_sql)
        # 旧版 conversations 表没有 session_id，这里会自动补上。
        _ensure_conversations_session_id_column(connection)
        # 把旧数据按 user_id 归入一个“默认会话”。
        _migrate_existing_conversations_to_default_sessions(connection)
        connection.execute(create_sessions_index_sql)
        connection.execute(create_conversations_session_index_sql)
        connection.execute(create_conversations_user_index_sql)
        connection.execute(create_session_summaries_last_conversation_index_sql)
        connection.execute(create_interview_jds_user_index_sql)
        connection.execute(create_documents_user_session_index_sql)
        connection.execute(create_documents_status_index_sql)
        connection.execute(create_documents_expires_at_index_sql)
        connection.commit()
    finally:
        connection.close()


def _ensure_chat_sessions_subject_column(connection: sqlite3.Connection) -> None:
    """Add the nullable subject column to legacy chat_sessions tables."""

    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({CHAT_SESSIONS_TABLE})")
    }
    if "subject" not in columns:
        connection.execute(
            f"ALTER TABLE {CHAT_SESSIONS_TABLE} ADD COLUMN subject TEXT"
        )


def _ensure_conversations_session_id_column(connection: sqlite3.Connection) -> None:
    """给旧版 conversations 表补上 session_id 字段。"""

    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
    }

    if "session_id" not in columns:
        connection.execute(
            f"ALTER TABLE {CONVERSATIONS_TABLE} ADD COLUMN session_id INTEGER"
        )


def _ensure_chat_sessions_persona_id_column(connection: sqlite3.Connection) -> None:
    """给旧版 chat_sessions 表补上 persona_id 字段。"""

    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({CHAT_SESSIONS_TABLE})")
    }

    if "persona_id" not in columns:
        connection.execute(
            f"""
            ALTER TABLE {CHAT_SESSIONS_TABLE}
            ADD COLUMN persona_id TEXT NOT NULL DEFAULT 'tutor'
            """
        )


def _migrate_existing_conversations_to_default_sessions(
    connection: sqlite3.Connection,
) -> None:
    """把旧的用户历史记录迁移到每个用户自己的默认会话。"""

    users_with_old_rows = connection.execute(
        f"""
        SELECT
            user_id,
            MIN(created_at) AS first_created_at,
            MAX(created_at) AS last_created_at
        FROM {CONVERSATIONS_TABLE}
        WHERE session_id IS NULL
        GROUP BY user_id
        """
    ).fetchall()

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
            f"""
            UPDATE {CONVERSATIONS_TABLE}
            SET session_id = ?
            WHERE user_id = ? AND session_id IS NULL
            """,
            (session_id, user_id),
        )


def _get_or_create_default_session_id(
    connection: sqlite3.Connection,
    user_id: str,
    created_at: str,
    updated_at: str,
) -> int:
    """获取某个用户的默认会话 id；没有就创建。"""

    row = connection.execute(
        f"""
        SELECT id
        FROM {CHAT_SESSIONS_TABLE}
        WHERE user_id = ? AND title = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id, DEFAULT_SESSION_TITLE),
    ).fetchone()

    if row is not None:
        # 如果默认会话已存在，就把更新时间推进到旧数据的最新时间。
        connection.execute(
            f"""
            UPDATE {CHAT_SESSIONS_TABLE}
            SET updated_at = MAX(updated_at, ?)
            WHERE id = ?
            """,
            (updated_at, row["id"]),
        )
        return int(row["id"])

    cursor = connection.execute(
        f"""
        INSERT INTO {CHAT_SESSIONS_TABLE}
            (user_id, title, persona_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, DEFAULT_SESSION_TITLE, "tutor", created_at, updated_at),
    )
    new_id = cursor.lastrowid

    if new_id is None:
        raise RuntimeError("创建默认会话失败：没有拿到新记录 id")

    return new_id
