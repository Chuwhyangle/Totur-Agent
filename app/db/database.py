"""SQLite connection and schema initialization."""

from pathlib import Path
import sqlite3

from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DEFAULT_SESSION_TITLE,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "tutor_agent.db"


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection for the app database."""

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database() -> None:
    """Create database tables if they do not already exist."""

    create_sessions_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {CHAT_SESSIONS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
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

    connection = get_connection()
    try:
        connection.execute(create_sessions_table_sql)
        connection.execute(create_conversations_table_sql)
        _ensure_conversations_session_id_column(connection)
        _migrate_existing_conversations_to_default_sessions(connection)
        connection.execute(create_sessions_index_sql)
        connection.execute(create_conversations_session_index_sql)
        connection.execute(create_conversations_user_index_sql)
        connection.commit()
    finally:
        connection.close()


def _ensure_conversations_session_id_column(connection: sqlite3.Connection) -> None:
    """Add session_id to old conversations tables created before sessions existed."""

    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
    }

    if "session_id" not in columns:
        connection.execute(
            f"ALTER TABLE {CONVERSATIONS_TABLE} ADD COLUMN session_id INTEGER"
        )


def _migrate_existing_conversations_to_default_sessions(
    connection: sqlite3.Connection,
) -> None:
    """Move old user-only conversation rows into one default session per user."""

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
    """Return the default session id for one user, creating it if needed."""

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
        INSERT INTO {CHAT_SESSIONS_TABLE} (user_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, DEFAULT_SESSION_TITLE, created_at, updated_at),
    )
    new_id = cursor.lastrowid

    if new_id is None:
        raise RuntimeError("创建默认会话失败：没有拿到新记录 id")

    return new_id
