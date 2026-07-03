"""Conversation history database operations."""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import ConversationRecord, CONVERSATIONS_TABLE


def save_conversation(
    user_id: str,
    message: str,
    reply_json: str,
) -> int:
    """Save one conversation and return its new database id."""
    initialize_database()
    insert_sql = f"""
    INSERT INTO {CONVERSATIONS_TABLE} (user_id, message, reply_json, created_at)
    VALUES(?,?,?,?)
    """
    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        cursor = connection.execute(
            insert_sql,
            (user_id, message, reply_json, created_at),
        )
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("保存对话失败：没有拿到新记录 id")

        return new_id
    finally:
        connection.close()


def list_recent_conversations(
    user_id: str,
    limit: int = 20,
) -> list[ConversationRecord]:
    """Return recent conversations for a user, newest first."""
    initialize_database()
    select_sql = f"""
    SELECT id, user_id, message, reply_json, created_at
    FROM {CONVERSATIONS_TABLE}
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT ?
"""
    connection = get_connection()
    try:
        cursor = connection.execute(
            select_sql,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        conversations = [
            ConversationRecord(
                id=row["id"],
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
