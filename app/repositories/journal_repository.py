"""Journal entries 数据库 CRUD 操作。"""

from datetime import datetime, timezone

from sqlalchemy import text

from app.db.database import initialize_database
from app.db.engine import get_engine
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
    VALUES (
        :session_id,
        :persona_id,
        :title,
        :content,
        :tags,
        :entry_date,
        :created_at,
        :updated_at
    )
    """
    values = {
        "session_id": session_id,
        "persona_id": persona_id,
        "title": title,
        "content": content,
        "tags": tags,
        "entry_date": entry_date,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        cursor = connection.execute(text(insert_sql), values)
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


def get_journal_entry(entry_id: int) -> JournalEntryRecord | None:
    """根据 id 获取单条日记。"""

    initialize_database()
    select_sql = f"""
    SELECT id, session_id, persona_id, title, content, tags, entry_date, created_at, updated_at
    FROM {JOURNAL_ENTRIES_TABLE}
    WHERE id = :id
    """

    with get_engine().connect() as connection:
        row = connection.execute(
            text(select_sql),
            {"id": entry_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return _record_from_row(row)


def list_journal_entries(
    date: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[JournalEntryRecord]:
    """查询日记列表，支持按日期和标签过滤。"""

    initialize_database()
    conditions = []
    params: dict[str, object] = {}

    if date:
        conditions.append("entry_date = :entry_date")
        params["entry_date"] = date
    if tag:
        # 标签是逗号分隔的，用 LIKE 模糊匹配
        conditions.append(
            "(tags LIKE :tag_pattern OR tags LIKE :tag_comma_end "
            "OR tags LIKE :tag_comma_start OR tags = :tag)"
        )
        tag_pattern = f"%{tag}%"
        params.update(
            {
                "tag_pattern": tag_pattern,
                "tag_comma_end": f"{tag},%",
                "tag_comma_start": f",%{tag}",
                "tag": tag,
            }
        )

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    select_sql = f"""
    SELECT id, session_id, persona_id, title, content, tags, entry_date, created_at, updated_at
    FROM {JOURNAL_ENTRIES_TABLE}
    {where_clause}
    ORDER BY entry_date DESC, id DESC
    LIMIT :limit
    """
    params["limit"] = limit

    with get_engine().connect() as connection:
        rows = connection.execute(
            text(select_sql),
            params,
        ).mappings().fetchall()
        return [_record_from_row(row) for row in rows]


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
    params: dict[str, object] = {}

    if title is not None:
        updates.append("title = :title")
        params["title"] = title
    if content is not None:
        updates.append("content = :content")
        params["content"] = content
    if tags is not None:
        updates.append("tags = :tags")
        params["tags"] = tags
    if entry_date is not None:
        updates.append("entry_date = :entry_date")
        params["entry_date"] = entry_date

    if not updates:
        return get_journal_entry(entry_id)

    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = :updated_at")
    params["updated_at"] = now
    params["id"] = entry_id

    update_sql = f"""
    UPDATE {JOURNAL_ENTRIES_TABLE}
    SET {', '.join(updates)}
    WHERE id = :id
    """

    with get_engine().begin() as connection:
        connection.execute(text(update_sql), params)

    # 事务提交后再读回，避免读到未提交的旧值。
    return get_journal_entry(entry_id)


def delete_journal_entry(entry_id: int) -> bool:
    """删除一条日记。返回是否删除成功。"""

    initialize_database()
    delete_sql = f"DELETE FROM {JOURNAL_ENTRIES_TABLE} WHERE id = :id"

    with get_engine().begin() as connection:
        cursor = connection.execute(
            text(delete_sql),
            {"id": entry_id},
        )
        return cursor.rowcount > 0


def _record_from_row(row) -> JournalEntryRecord:
    """把查询结果行转成 JournalEntryRecord。"""

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
