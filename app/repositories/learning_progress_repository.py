"""学习进度记录的数据库读写。"""

from datetime import datetime, timezone

from sqlalchemy import text

from app.db.engine import get_engine
from app.db.models import (
    LEARNING_PROGRESS_TABLE,
    LearningProgressRecord,
    LearningProgressSource,
    LearningProgressStatus,
)


def list_learning_progress(
    user_id: str,
    subject: str = "sql",
    limit: int = 100,
) -> list[LearningProgressRecord]:
    """读取一个用户在某个主题下的学习进度。"""

    query = text(
        f"""
        SELECT id, user_id, subject, topic, level, status,
               evidence, next_step, source, updated_at
        FROM {LEARNING_PROGRESS_TABLE}
        WHERE user_id = :user_id AND subject = :subject
        ORDER BY updated_at DESC, id DESC
        LIMIT :limit
        """
    )
    with get_engine().connect() as connection:
        rows = connection.execute(
            query,
            {"user_id": user_id, "subject": subject, "limit": limit},
        ).mappings().fetchall()
    return [_record_from_row(row) for row in rows]


def get_learning_progress(
    user_id: str,
    subject: str,
    topic: str,
) -> LearningProgressRecord | None:
    """读取一个知识点的学习进度。"""

    query = text(
        f"""
        SELECT id, user_id, subject, topic, level, status,
               evidence, next_step, source, updated_at
        FROM {LEARNING_PROGRESS_TABLE}
        WHERE user_id = :user_id AND subject = :subject AND topic = :topic
        """
    )
    with get_engine().connect() as connection:
        row = connection.execute(
            query,
            {"user_id": user_id, "subject": subject, "topic": topic},
        ).mappings().fetchone()
    return _record_from_row(row) if row is not None else None


def upsert_learning_progress(
    *,
    user_id: str,
    subject: str,
    topic: str,
    level: int,
    status: LearningProgressStatus | str,
    evidence: str | None,
    next_step: str | None,
    source: LearningProgressSource | str,
) -> LearningProgressRecord:
    """新增或更新一个知识点，按 user_id + subject + topic 去重。"""

    now = _now()
    status_value = LearningProgressStatus(status).value
    source_value = LearningProgressSource(source).value
    values = {
        "user_id": user_id,
        "subject": subject,
        "topic": topic,
        "level": level,
        "status": status_value,
        "evidence": evidence,
        "next_step": next_step,
        "source": source_value,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        existing = connection.execute(
            text(
                f"""
                SELECT id FROM {LEARNING_PROGRESS_TABLE}
                WHERE user_id = :user_id AND subject = :subject AND topic = :topic
                """
            ),
            {"user_id": user_id, "subject": subject, "topic": topic},
        ).mappings().fetchone()

        if existing is None:
            result = connection.execute(
                text(
                    f"""
                    INSERT INTO {LEARNING_PROGRESS_TABLE} (
                        user_id, subject, topic, level, status,
                        evidence, next_step, source, updated_at
                    ) VALUES (
                        :user_id, :subject, :topic, :level, :status,
                        :evidence, :next_step, :source, :updated_at
                    )
                    """
                ),
                values,
            )
            record_id = result.lastrowid
            if record_id is None:
                raise RuntimeError("创建学习进度失败：没有拿到新记录 id")
        else:
            record_id = existing["id"]
            connection.execute(
                text(
                    f"""
                    UPDATE {LEARNING_PROGRESS_TABLE}
                    SET level = :level,
                        status = :status,
                        evidence = :evidence,
                        next_step = :next_step,
                        source = :source,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {**values, "id": record_id},
            )

    return LearningProgressRecord(
        id=record_id,
        user_id=user_id,
        subject=subject,
        topic=topic,
        level=level,
        status=LearningProgressStatus(status_value),
        evidence=evidence,
        next_step=next_step,
        source=LearningProgressSource(source_value),
        updated_at=now,
    )


def delete_learning_progress(
    *,
    progress_id: int,
    user_id: str,
    subject: str,
) -> bool:
    """删除属于指定用户和主题的一条学习进度。"""

    query = text(
        f"""
        DELETE FROM {LEARNING_PROGRESS_TABLE}
        WHERE id = :id AND user_id = :user_id AND subject = :subject
        """
    )
    with get_engine().begin() as connection:
        result = connection.execute(
            query,
            {"id": progress_id, "user_id": user_id, "subject": subject},
        )
    return result.rowcount > 0


def _record_from_row(row) -> LearningProgressRecord:
    """把数据库结果转换为领域记录。"""

    return LearningProgressRecord(
        id=row["id"],
        user_id=row["user_id"],
        subject=row["subject"],
        topic=row["topic"],
        level=int(row["level"]),
        status=LearningProgressStatus(row["status"]),
        evidence=row["evidence"],
        next_step=row["next_step"],
        source=LearningProgressSource(row["source"]),
        updated_at=str(row["updated_at"]),
    )


def _now() -> str:
    """使用 SQLite 和 MySQL DATETIME 都能接受的 UTC 字符串。"""

    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
