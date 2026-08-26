"""聊天会话数据库操作。"""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DEFAULT_SESSION_TITLE,
    DOCUMENTS_TABLE,
    TASKS_TABLE,
    ChatSessionRecord,
)
from app.services.agent.personas import DEFAULT_PERSONA_ID


SESSION_TITLE_MAX_LENGTH = 30


class SessionDeleteBlockedError(RuntimeError):
    """A session still owns resources that must be cleaned up first."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Session deletion is blocked by {reason}")


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
    workspace_id: str | None = None,
    *,
    conn: Connection | None = None,
) -> ChatSessionRecord:
    """为某个用户创建一个聊天会话。

    传入 conn 时复用调用方的连接与事务；不传则自行开启事务。
    """

    now = datetime.now(timezone.utc).isoformat()
    # 如果前端没有传标题，就先使用默认会话标题。
    session_title = title.strip() if title and title.strip() else DEFAULT_SESSION_TITLE
    insert_sql = f"""
    INSERT INTO {CHAT_SESSIONS_TABLE}
        (user_id, title, persona_id, created_at, updated_at, subject, workspace_id)
    VALUES (
        :user_id, :title, :persona_id, :created_at, :updated_at,
        :subject, :workspace_id
    )
    """
    params = {
        "user_id": user_id,
        "title": session_title,
        "persona_id": persona_id,
        "created_at": now,
        "updated_at": now,
        "subject": subject,
        "workspace_id": workspace_id,
    }

    def _execute(cursor_connection: Connection) -> int:
        cursor = cursor_connection.execute(text(insert_sql), params)
        new_id = cursor.lastrowid
        if new_id is None:
            raise RuntimeError("创建会话失败：没有拿到新记录 id")
        return new_id

    if conn is not None:
        new_id = _execute(conn)
    else:
        with get_engine().begin() as connection:
            new_id = _execute(connection)

    return ChatSessionRecord(
        id=new_id,
        user_id=user_id,
        title=session_title,
        persona_id=persona_id,
        created_at=now,
        updated_at=now,
        subject=subject,
        workspace_id=workspace_id,
        archived_at=None,
    )


def get_or_create_default_session(
    user_id: str,
    persona_id: str = DEFAULT_PERSONA_ID,
    subject: str | None = None,
    *,
    conn: Connection | None = None,
) -> ChatSessionRecord:
    """获取某个用户的默认会话；没有就自动创建。

    传入 conn 时复用调用方的连接与事务，并透传给 create_session。
    """

    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at,
           subject, workspace_id, archived_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE user_id = :user_id
      AND title = :title
      AND persona_id = :persona_id
      AND workspace_id IS NULL
      AND archived_at IS NULL
    ORDER BY id ASC
    LIMIT 1
    """
    select_params = {
        "user_id": user_id,
        "title": DEFAULT_SESSION_TITLE,
        "persona_id": persona_id,
    }

    if conn is not None:
        row = conn.execute(
            text(select_sql),
            select_params,
        ).mappings().fetchone()

        if row is not None:
            return _session_from_row(row)

        # 旧版 /chat 不传 session_id 时，会走到这里创建默认会话。
        return create_session(
            user_id=user_id,
            title=DEFAULT_SESSION_TITLE,
            persona_id=persona_id,
            conn=conn,
        )

    with get_engine().connect() as connection:
        row = connection.execute(
            text(select_sql),
            select_params,
        ).mappings().fetchone()

    if row is not None:
        return _session_from_row(row)

    # 旧版 /chat 不传 session_id 时，会走到这里创建默认会话。
    return create_session(
        user_id=user_id,
        title=DEFAULT_SESSION_TITLE,
        persona_id=persona_id,
    )


def get_session(
    session_id: int,
    user_id: str | None = None,
) -> ChatSessionRecord | None:
    """根据 session_id 查询一个会话，可选按用户限制访问范围。"""

    conditions = ["id = :id"]
    params: dict[str, object] = {"id": session_id}
    if user_id is not None:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at,
           subject, workspace_id, archived_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE {' AND '.join(conditions)}
    """
    with get_engine().connect() as connection:
        row = connection.execute(text(select_sql), params).mappings().fetchone()
    return _session_from_row(row) if row is not None else None


def get_session_for_update(
    session_id: int,
    *,
    conn: Connection,
) -> ChatSessionRecord | None:
    """Fetch a session in the caller's transaction, locking it on MySQL."""

    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at,
           subject, workspace_id, archived_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE id = :id
    """
    if conn.dialect.name == "mysql":
        select_sql = f"{select_sql} FOR UPDATE"

    row = conn.execute(
        text(select_sql),
        {"id": session_id},
    ).mappings().fetchone()
    return _session_from_row(row) if row is not None else None


def list_sessions(
    user_id: str,
    limit: int = 50,
    *,
    include_archived: bool = False,
) -> list[ChatSessionRecord]:
    """查询某个用户最近的会话，默认隐藏已回档会话。"""

    archived_filter = "" if include_archived else " AND archived_at IS NULL"
    select_sql = f"""
    SELECT id, user_id, title, persona_id, created_at, updated_at,
           subject, workspace_id, archived_at
    FROM {CHAT_SESSIONS_TABLE}
    WHERE user_id = :user_id{archived_filter}
    ORDER BY updated_at DESC, id DESC
    LIMIT :limit
    """

    with get_engine().connect() as connection:
        rows = connection.execute(
            text(select_sql),
            {"user_id": user_id, "limit": limit},
        ).mappings().fetchall()

        return [_session_from_row(row) for row in rows]


def archive_session(session_id: int, user_id: str) -> ChatSessionRecord | None:
    """将属于指定用户的会话回档，保留全部历史数据。"""

    session = get_session(session_id=session_id, user_id=user_id)
    if session is None or session.archived_at is not None:
        return session

    now = datetime.now(timezone.utc).isoformat()
    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET archived_at = :archived_at
    WHERE id = :id AND user_id = :user_id AND archived_at IS NULL
    """
    with get_engine().begin() as connection:
        connection.execute(
            text(update_sql),
            {"id": session_id, "user_id": user_id, "archived_at": now},
        )
    return get_session(session_id=session_id, user_id=user_id)


def restore_session(session_id: int, user_id: str) -> ChatSessionRecord | None:
    """恢复属于指定用户的已回档会话。"""

    session = get_session(session_id=session_id, user_id=user_id)
    if session is None or session.archived_at is None:
        return session

    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET archived_at = NULL
    WHERE id = :id AND user_id = :user_id AND archived_at IS NOT NULL
    """
    with get_engine().begin() as connection:
        connection.execute(
            text(update_sql),
            {"id": session_id, "user_id": user_id},
        )
    return get_session(session_id=session_id, user_id=user_id)


def delete_session(session_id: int, user_id: str) -> bool:
    """永久删除会话及其聊天记录，返回是否实际删除。"""

    with get_engine().begin() as connection:
        session = connection.execute(
            text(
                f"SELECT id FROM {CHAT_SESSIONS_TABLE} "
                "WHERE id = :id AND user_id = :user_id"
            ),
            {"id": session_id, "user_id": user_id},
        ).mappings().fetchone()
        if session is None:
            return False

        attachment_count = connection.execute(
            text(
                f"SELECT COUNT(*) AS total FROM {DOCUMENTS_TABLE} "
                "WHERE session_id = :session_id "
                "AND scope = 'ATTACHMENT' AND status <> 'DELETED'"
            ),
            {"session_id": session_id},
        ).scalar_one()
        if attachment_count:
            raise SessionDeleteBlockedError("attachments")

        task_count = connection.execute(
            text(
                f"SELECT COUNT(*) AS total FROM {TASKS_TABLE} "
                "WHERE session_id = :session_id"
            ),
            {"session_id": session_id},
        ).scalar_one()
        if task_count:
            raise SessionDeleteBlockedError("workspace tasks")

        # DELETED attachment metadata has already completed file/vector cleanup.
        connection.execute(
            text(
                f"DELETE FROM {DOCUMENTS_TABLE} "
                "WHERE session_id = :session_id AND status = 'DELETED'"
            ),
            {"session_id": session_id},
        )
        connection.execute(
            text(
                "DELETE FROM session_summaries WHERE session_id = :session_id"
            ),
            {"session_id": session_id},
        )
        connection.execute(
            text(
                f"DELETE FROM {CONVERSATIONS_TABLE} "
                "WHERE session_id = :session_id"
            ),
            {"session_id": session_id},
        )
        cursor = connection.execute(
            text(
                f"DELETE FROM {CHAT_SESSIONS_TABLE} "
                "WHERE id = :id AND user_id = :user_id"
            ),
            {"id": session_id, "user_id": user_id},
        )
        return cursor.rowcount > 0


def touch_session(
    session_id: int,
    *,
    conn: Connection | None = None,
) -> None:
    """保存新对话后，更新会话的最后活跃时间。

    传入 conn 时复用调用方的连接与事务；不传则自行开启事务。
    """

    now = datetime.now(timezone.utc).isoformat()
    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET updated_at = :updated_at
    WHERE id = :id
    """
    params = {"updated_at": now, "id": session_id}

    if conn is not None:
        conn.execute(text(update_sql), params)
        return

    with get_engine().begin() as connection:
        connection.execute(text(update_sql), params)


def update_session_title(session_id: int, title: str) -> None:
    """更新会话标题。"""

    update_sql = f"""
    UPDATE {CHAT_SESSIONS_TABLE}
    SET title = :title
    WHERE id = :id
    """

    with get_engine().begin() as connection:
        connection.execute(
            text(update_sql),
            {"title": title, "id": session_id},
        )


def _session_from_row(row) -> ChatSessionRecord:
    """把查询结果行转成 ChatSessionRecord。"""

    return ChatSessionRecord(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        persona_id=row["persona_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        subject=row["subject"],
        workspace_id=row["workspace_id"],
        archived_at=row["archived_at"],
    )
