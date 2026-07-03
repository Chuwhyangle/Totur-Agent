"""Conversation history database operations."""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import ConversationRecord, CONVERSATIONS_TABLE
from app.repositories.session_repository import (
    get_or_create_default_session,
    touch_session,
)


def save_conversation(
    user_id: str,
    message: str,
    reply_json: str,
    session_id: int | None = None,
) -> int:
    """Save one conversation and return its new database id."""
    initialize_database()
    conversation_session_id = session_id

    if conversation_session_id is None:
        conversation_session_id = get_or_create_default_session(user_id).id

    insert_sql = f"""
    INSERT INTO {CONVERSATIONS_TABLE}
        (session_id, user_id, message, reply_json, created_at)
    VALUES (?, ?, ?, ?, ?)
    """
    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        cursor = connection.execute(
            insert_sql,
            (conversation_session_id, user_id, message, reply_json, created_at),
        )
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("保存对话失败：没有拿到新记录 id")

        touch_session(conversation_session_id)

        return new_id
    finally:
        connection.close()


def list_recent_conversations(
    user_id: str,
    limit: int = 20,
    session_id: int | None = None,
) -> list[ConversationRecord]:
    """Return recent conversations for a user, newest first."""
    initialize_database()
    where_sql = "WHERE user_id = ?"
    params: tuple[str, int] | tuple[str, int, int] = (user_id, limit)

    if session_id is not None:
        where_sql = "WHERE user_id = ? AND session_id = ?"
        params = (user_id, session_id, limit)

    select_sql = f"""
    SELECT id, session_id, user_id, message, reply_json, created_at
    FROM {CONVERSATIONS_TABLE}
    {where_sql}
    ORDER BY id DESC
    LIMIT ?
    """
    connection = get_connection()
    try:
        cursor = connection.execute(
            select_sql,
            params,
        )
        rows = cursor.fetchall()
        conversations = [
            ConversationRecord(
                id=row["id"],
                session_id=row["session_id"],
                user_id=row["user_id"],
                message=row["message"],
                reply_json=row["reply_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return conversations
    finally:
        connection.close()
