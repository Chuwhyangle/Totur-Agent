"""Journal entries 数据库 CRUD 操作。"""

from datetime import datetime, timezone

from app.db.database import get_connection, initialize_database
from app.db.models import JOURNAL_ENTRIES_TABLE, JournalEntryRecord


def create_journal_entry(
    title: str,
    content: str,
    entry_date: str,
    session_id: int | None = None,
    persona_id: str = "journal",
    tags: str = "",
) -> JournalEntryRecord:
    """创建一条日记记录。"""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    insert_sql = f"""
    INSERT INTO {JOURNAL_ENTRIES_TABLE} (
        session_id,
        persona_id,
        title,
        content,
        tags,
        entry_date,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (session_id, persona_id, title, content, tags, entry_date, now, now)
    connection = get_connection()

    try:
        cursor = connection.execute(insert_sql, values)
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("创建日记失败：没有拿到新记录 id")

        return JournalEntryRecord(
            id=new_id,
            session_id=session_id,
            persona_id=persona_id,
            title=title,
            content=content,
            tags=tags,
            entry_date=entry_date,
            created_at=now,
            updated_at=now,
        )
    finally:
        connection.close()


def get_journal_entry(entry_id: int) -> JournalEntryRecord | None:
    """根据 id 获取单条日记。"""

    initialize_database()
    select_sql = f"""
    SELECT id, session_id, persona_id, title, content, tags, entry_date, created_at, updated_at
    FROM {JOURNAL_ENTRIES_TABLE}
    WHERE id = ?
    """
    connection = get_connection()

    try:
        row = connection.execute(select_sql, (entry_id,)).fetchone()
        if row is None:
            return None
        return _record_from_row(row)
    finally:
        connection.close()


def list_journal_entries(
    date: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[JournalEntryRecord]:
    """查询日记列表，支持按日期和标签过滤。"""

    initialize_database()
    conditions = []
    params: list = []

    if date:
        conditions.append("entry_date = ?")
        params.append(date)
    if tag:
        # 标签是逗号分隔的，用 LIKE 模糊匹配
        conditions.append("(tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)")
        tag_pattern = f"%{tag}%"
        params.extend([tag_pattern, f"{tag},%", f",%{tag}", tag])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    select_sql = f"""
    SELECT id, session_id, persona_id, title, content, tags, entry_date, created_at, updated_at
    FROM {JOURNAL_ENTRIES_TABLE}
    {where_clause}
    ORDER BY entry_date DESC, id DESC
    LIMIT ?
    """
    params.append(limit)

    connection = get_connection()

    try:
        rows = connection.execute(select_sql, params).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def update_journal_entry(
    entry_id: int,
    title: str | None = None,
    content: str | None = None,
    tags: str | None = None,
    entry_date: str | None = None,
) -> JournalEntryRecord | None:
    """更新一条日记。"""

    initialize_database()
    updates = []
    params: list = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)
    if entry_date is not None:
        updates.append("entry_date = ?")
        params.append(entry_date)

    if not updates:
        return get_journal_entry(entry_id)

    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(entry_id)

    update_sql = f"""
    UPDATE {JOURNAL_ENTRIES_TABLE}
    SET {', '.join(updates)}
    WHERE id = ?
    """
    connection = get_connection()

    try:
        connection.execute(update_sql, params)
        connection.commit()
        return get_journal_entry(entry_id)
    finally:
        connection.close()


def delete_journal_entry(entry_id: int) -> bool:
    """删除一条日记。返回是否删除成功。"""

    initialize_database()
    delete_sql = f"DELETE FROM {JOURNAL_ENTRIES_TABLE} WHERE id = ?"
    connection = get_connection()

    try:
        cursor = connection.execute(delete_sql, (entry_id,))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def _record_from_row(row) -> JournalEntryRecord:
    """把 sqlite3.Row 转成 JournalEntryRecord。"""

    return JournalEntryRecord(
        id=row["id"],
        session_id=row["session_id"],
        persona_id=row["persona_id"],
        title=row["title"],
        content=row["content"],
        tags=row["tags"],
        entry_date=row["entry_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
