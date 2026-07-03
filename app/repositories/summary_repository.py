"""会话滚动摘要的数据访问函数。"""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import (
    CONVERSATIONS_TABLE,
    SESSION_SUMMARIES_TABLE,
    ConversationRecord,
    SessionSummaryRecord,
)


def get_summary(session_id: int) -> SessionSummaryRecord | None:
    """查询某个会话当前保存的摘要；没有摘要时返回 None。"""

    initialize_database()
    select_sql = f"""
    SELECT id, session_id, summary_text, last_conversation_id, created_at, updated_at
    FROM {SESSION_SUMMARIES_TABLE}
    WHERE session_id = ?
    """
    connection = get_connection()

    try:
        row = connection.execute(select_sql, (session_id,)).fetchone()

        if row is None:
            return None

        return _summary_from_row(row)
    finally:
        connection.close()


def upsert_summary(
    session_id: int,
    summary_text: str,
    last_conversation_id: int,
) -> int:
    """新增或更新某个会话的滚动摘要，并返回摘要记录 id。"""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    select_sql = f"""
    SELECT id
    FROM {SESSION_SUMMARIES_TABLE}
    WHERE session_id = ?
    """
    insert_sql = f"""
    INSERT INTO {SESSION_SUMMARIES_TABLE}
        (session_id, summary_text, last_conversation_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?)
    """
    update_sql = f"""
    UPDATE {SESSION_SUMMARIES_TABLE}
    SET summary_text = ?,
        last_conversation_id = ?,
        updated_at = ?
    WHERE session_id = ?
    """
    connection = get_connection()

    try:
        existing_row = connection.execute(select_sql, (session_id,)).fetchone()

        if existing_row is None:
            cursor = connection.execute(
                insert_sql,
                (session_id, summary_text, last_conversation_id, now, now),
            )
            new_id = cursor.lastrowid

            if new_id is None:
                raise RuntimeError("保存会话摘要失败：没有拿到新记录 id")

            summary_id = new_id
        else:
            summary_id = int(existing_row["id"])
            connection.execute(
                update_sql,
                (summary_text, last_conversation_id, now, session_id),
            )

        connection.commit()
        return summary_id
    finally:
        connection.close()


def count_unsummarized_conversations(session_id: int, after_id: int) -> int:
    """统计某个会话里 id 大于 after_id、还没进入摘要的对话条数。"""

    initialize_database()
    select_sql = f"""
    SELECT COUNT(*) AS total
    FROM {CONVERSATIONS_TABLE}
    WHERE session_id = ? AND id > ?
    """
    connection = get_connection()

    try:
        row = connection.execute(select_sql, (session_id, after_id)).fetchone()
        return int(row["total"])
    finally:
        connection.close()


def list_conversations_after(
    session_id: int,
    after_id: int,
    limit: int,
) -> list[ConversationRecord]:
    """按时间从旧到新读取某个会话中 id 大于 after_id 的对话。"""

    initialize_database()
    select_sql = f"""
    SELECT id, session_id, user_id, message, reply_json, created_at
    FROM {CONVERSATIONS_TABLE}
    WHERE session_id = ? AND id > ?
    ORDER BY id ASC
    LIMIT ?
    """
    connection = get_connection()

    try:
        rows = connection.execute(select_sql, (session_id, after_id, limit)).fetchall()
        return [_conversation_from_row(row) for row in rows]
    finally:
        connection.close()


def _summary_from_row(row) -> SessionSummaryRecord:
    """把 sqlite3.Row 转成摘要记录对象。"""

    return SessionSummaryRecord(
        id=row["id"],
        session_id=row["session_id"],
        summary_text=row["summary_text"],
        last_conversation_id=row["last_conversation_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _conversation_from_row(row) -> ConversationRecord:
    """把 sqlite3.Row 转成对话记录对象。"""

    return ConversationRecord(
        id=row["id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        message=row["message"],
        reply_json=row["reply_json"],
        created_at=row["created_at"],
    )
