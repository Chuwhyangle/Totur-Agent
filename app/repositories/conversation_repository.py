"""对话历史数据库操作。"""

from datetime import datetime, timezone

from sqlalchemy import text

from app.db.engine import get_engine
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
    """保存一条对话，并返回新记录 id。

    INSERT、默认会话创建、会话时间更新在同一个事务内，同生共死。
    """

    insert_sql = f"""
    INSERT INTO {CONVERSATIONS_TABLE}
        (session_id, user_id, message, reply_json, created_at)
    VALUES (:session_id, :user_id, :message, :reply_json, :created_at)
    """
    created_at = datetime.now(timezone.utc).isoformat()

    with get_engine().begin() as connection:
        conversation_session_id = session_id
        if conversation_session_id is None:
            # 兼容旧版 /chat：没传 session_id 时自动进入默认会话。
            conversation_session_id = get_or_create_default_session(
                user_id, conn=connection
            ).id

        cursor = connection.execute(
            text(insert_sql),
            {
                "session_id": conversation_session_id,
                "user_id": user_id,
                "message": message,
                "reply_json": reply_json,
                "created_at": created_at,
            },
        )
        new_id = cursor.lastrowid
        if new_id is None:
            raise RuntimeError("保存对话失败：没有拿到新记录 id")

        # 有新消息后，更新会话的最后活跃时间，方便会话列表按最近排序。
        touch_session(conversation_session_id, conn=connection)

    return new_id


def list_recent_conversations(
    user_id: str,
    limit: int = 20,
    session_id: int | None = None,
) -> list[ConversationRecord]:
    """查询最近对话；传 session_id 时只查该会话。"""
    where_sql = "WHERE user_id = :user_id"
    params: dict = {"user_id": user_id, "limit": limit}

    if session_id is not None:
        # 多会话模式下，历史边界是 user_id + session_id。
        where_sql = "WHERE user_id = :user_id AND session_id = :session_id"
        params = {"user_id": user_id, "session_id": session_id, "limit": limit}

    select_sql = f"""
    SELECT id, session_id, user_id, message, reply_json, created_at
    FROM {CONVERSATIONS_TABLE}
    {where_sql}
    ORDER BY id DESC
    LIMIT :limit
    """
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(select_sql),
            params,
        ).mappings().fetchall()
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
