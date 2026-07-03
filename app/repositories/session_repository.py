"""Chat session database operations."""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    DEFAULT_SESSION_TITLE,
    ChatSessionRecord,
)


SESSION_TITLE_MAX_LENGTH = 30


def make_title_from_message(message: str) -> str:
    """Use the first user message as a short session title."""

    title = " ".join(message.strip().split())
    if not title:
        return DEFAULT_SESSION_TITLE

    if len(title) <= SESSION_TITLE_MAX_LENGTH:
        return title

    return f"{title[:SESSION_TITLE_MAX_LENGTH]}..."


def create_session(
    user_id: str,
    title: str | None = None,
) -> ChatSessionRecord:
    """Create one chat session for a user."""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    session_title = title.strip() if title and title.strip() else DEFAULT_SESSION_TITLE
    insert_sql = f"""
    INSERT INTO {CHAT_SESSIONS_TABLE} (user_id, title, created_at, updated_at)
    VALUES (?, ?, ?, ?)
    """
    connection = get_connection()

    try:
        cursor = connection.execute(
            insert_sql,
            (user_id, session_title, now, now),
        )
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("创建会话失败：没有拿到新记录 id")

        return ChatSessionRecord(
            id=new_id,
            user_id=user_id,
            title=session_title,
            created_at=now,
            updated_at=now,
        )
    finally:
        connection.close()


def get_or_create_default_session(user_id: str) -> ChatSessionRecord:
    """Return one user's default session, creating it if needed."""

    initialize_database()
    select_sql = f"""
    SELECT id, user_id, title, created_at, updated_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE user_id = ? AND title = ?
    ORDER BY id ASC
    LIMIT 1
    """
    connection = get_connection()

    try:
        row = connection.execute(
            select_sql,
            (user_id, DEFAULT_SESSION_TITLE),
        ).fetchone()
    finally:
        connection.close()

    if row is not None:
        return _session_from_row(row)

    return create_session(user_id=user_id, title=DEFAULT_SESSION_TITLE)


def list_sessions(user_id: str, limit: int = 50) -> list[ChatSessionRecord]:
    """Return recent chat sessions for a user, newest first."""

    initialize_database()
    select_sql = f"""
    SELECT id, user_id, title, created_at, updated_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE user_id = ?
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    """
    connection = get_connection()

    try:
        rows = connection.execute(
            select_sql,
            (user_id, limit),
        ).fetchall()

        return [_session_from_row(row) for row in rows]
    finally:
        connection.close()


def touch_session(session_id: int) -> None:
    """Update a session timestamp after a new conversation is saved."""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET updated_at = ?
    WHERE id = ?
    """
    connection = get_connection()

    try:
        connection.execute(update_sql, (now, session_id))
        connection.commit()
    finally:
        connection.close()


def _session_from_row(row) -> ChatSessionRecord:
    return ChatSessionRecord(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
