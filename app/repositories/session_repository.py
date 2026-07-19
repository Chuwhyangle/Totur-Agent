"""聊天会话数据库操作。"""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    DEFAULT_SESSION_TITLE,
    ChatSessionRecord,
)
from app.services.agent.personas import DEFAULT_PERSONA_ID


SESSION_TITLE_MAX_LENGTH = 30


def make_title_from_message(message: str) -> str:
    """把用户第一条消息变成简短的会话标题。"""

    # 去掉首尾空白，并把中间连续空白压成一个空格。
    title = " ".join(message.strip().split())
    if not title:
        return DEFAULT_SESSION_TITLE

    if len(title) <= SESSION_TITLE_MAX_LENGTH:
        return title

    return f"{title[:SESSION_TITLE_MAX_LENGTH]}..."


def create_session(
    user_id: str,
    title: str | None = None,
    persona_id: str = DEFAULT_PERSONA_ID,
    subject: str | None = None,
) -> ChatSessionRecord:
    """为某个用户创建一个聊天会话。"""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    # 如果前端没有传标题，就先使用默认会话标题。
    session_title = title.strip() if title and title.strip() else DEFAULT_SESSION_TITLE
    insert_sql = f"""
    INSERT INTO {CHAT_SESSIONS_TABLE}
        (user_id, title, persona_id, created_at, updated_at, subject)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    connection = get_connection()

    try:
        cursor = connection.execute(
            insert_sql,
            (user_id, session_title, persona_id, now, now, subject),
        )
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("创建会话失败：没有拿到新记录 id")

        return ChatSessionRecord(
            id=new_id,
            user_id=user_id,
            title=session_title,
            persona_id=persona_id,
            created_at=now,
            updated_at=now,
            subject=subject,
        )
    finally:
        connection.close()


def get_or_create_default_session(
    user_id: str,
    persona_id: str = DEFAULT_PERSONA_ID,
    subject: str | None = None,
) -> ChatSessionRecord:
    """获取某个用户的默认会话；没有就自动创建。"""

    initialize_database()
    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at, subject
    FROM {CHAT_SESSIONS_TABLE}
    WHERE user_id = ? AND title = ? AND persona_id = ?
    ORDER BY id ASC
    LIMIT 1
    """
    connection = get_connection()

    try:
        row = connection.execute(
            select_sql,
            (user_id, DEFAULT_SESSION_TITLE, persona_id),
        ).fetchone()
    finally:
        connection.close()

    if row is not None:
        return _session_from_row(row)

    # 旧版 /chat 不传 session_id 时，会走到这里创建默认会话。
    return create_session(
        user_id=user_id,
        title=DEFAULT_SESSION_TITLE,
        persona_id=persona_id,
    )


def get_session(session_id: int) -> ChatSessionRecord | None:
    """根据 session_id 查询一个会话。"""

    initialize_database()
    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at, subject
    FROM {CHAT_SESSIONS_TABLE}
    WHERE id = ?
    """
    connection = get_connection()

    try:
        row = connection.execute(select_sql, (session_id,)).fetchone()

        if row is None:
            return None

        return _session_from_row(row)
    finally:
        connection.close()


def list_sessions(user_id: str, limit: int = 50) -> list[ChatSessionRecord]:
    """查询某个用户最近的会话列表，最新的排在前面。"""

    initialize_database()
    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at, subject
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
    """保存新对话后，更新会话的最后活跃时间。"""

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


def update_session_title(session_id: int, title: str) -> None:
    """更新会话标题。"""

    initialize_database()
    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET title = ?
    WHERE id = ?
    """
    connection = get_connection()

    try:
        connection.execute(update_sql, (title, session_id))
        connection.commit()
    finally:
        connection.close()


def _session_from_row(row) -> ChatSessionRecord:
    """把 sqlite3.Row 转成 ChatSessionRecord。"""

    return ChatSessionRecord(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        persona_id=row["persona_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        subject=row["subject"],
    )
