"""Interview JD 数据库操作。"""

from datetime import datetime, timezone
import json

from app.db.database import get_connection, initialize_database
from app.db.models import INTERVIEW_JDS_TABLE, InterviewJDRecord


def create_interview_jd(
    user_id: str,
    title: str,
    raw_text: str,
    role_family: str | None = None,
    seniority: str | None = None,
    target_graduation_years: list[str] | None = None,
    responsibilities: list[str] | None = None,
    must_have: list[str] | None = None,
    core_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
    bonus_skills: list[str] | None = None,
    keywords: list[str] | None = None,
    interview_focus: list[str] | None = None,
) -> InterviewJDRecord:
    """保存一条用户提供的目标岗位 JD。"""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    insert_sql = f"""
    INSERT INTO {INTERVIEW_JDS_TABLE} (
        user_id,
        title,
        role_family,
        seniority,
        target_graduation_years_json,
        raw_text,
        responsibilities_json,
        must_have_json,
        core_skills_json,
        preferred_skills_json,
        bonus_skills_json,
        keywords_json,
        interview_focus_json,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        user_id,
        title,
        role_family,
        seniority,
        _dump_list(target_graduation_years),
        raw_text,
        _dump_list(responsibilities),
        _dump_list(must_have),
        _dump_list(core_skills),
        _dump_list(preferred_skills),
        _dump_list(bonus_skills),
        _dump_list(keywords),
        _dump_list(interview_focus),
        now,
        now,
    )
    connection = get_connection()

    try:
        cursor = connection.execute(insert_sql, values)
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("创建 JD 失败：没有拿到新记录 id")

        return InterviewJDRecord(
            id=new_id,
            user_id=user_id,
            title=title,
            role_family=role_family,
            seniority=seniority,
            target_graduation_years=_clean_list(target_graduation_years),
            raw_text=raw_text,
            responsibilities=_clean_list(responsibilities),
            must_have=_clean_list(must_have),
            core_skills=_clean_list(core_skills),
            preferred_skills=_clean_list(preferred_skills),
            bonus_skills=_clean_list(bonus_skills),
            keywords=_clean_list(keywords),
            interview_focus=_clean_list(interview_focus),
            created_at=now,
            updated_at=now,
        )
    finally:
        connection.close()


def list_interview_jds(user_id: str, limit: int = 20) -> list[InterviewJDRecord]:
    """查询某个用户保存的最近 JD，最新的排在前面。"""

    initialize_database()
    select_sql = f"""
    SELECT
        id,
        user_id,
        title,
        role_family,
        seniority,
        target_graduation_years_json,
        raw_text,
        responsibilities_json,
        must_have_json,
        core_skills_json,
        preferred_skills_json,
        bonus_skills_json,
        keywords_json,
        interview_focus_json,
        created_at,
        updated_at
    FROM {INTERVIEW_JDS_TABLE}
    WHERE user_id = ?
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    """
    connection = get_connection()

    try:
        rows = connection.execute(select_sql, (user_id, limit)).fetchall()

        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def list_all_interview_jds(limit: int = 100) -> list[InterviewJDRecord]:
    """查询当前资料库里的 JD，供第一版工具全表检索。"""

    initialize_database()
    select_sql = f"""
    SELECT
        id,
        user_id,
        title,
        role_family,
        seniority,
        target_graduation_years_json,
        raw_text,
        responsibilities_json,
        must_have_json,
        core_skills_json,
        preferred_skills_json,
        bonus_skills_json,
        keywords_json,
        interview_focus_json,
        created_at,
        updated_at
    FROM {INTERVIEW_JDS_TABLE}
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    """
    connection = get_connection()

    try:
        rows = connection.execute(select_sql, (limit,)).fetchall()

        return [_record_from_row(row) for row in rows]
    finally:
        connection.close()


def _dump_list(values: list[str] | None) -> str:
    """把列表字段保存为 JSON，保留中文原文便于调试。"""

    return json.dumps(_clean_list(values), ensure_ascii=False)


def _clean_list(values: list[str] | None) -> list[str]:
    """去掉空字符串，避免表单里的空行污染检索数据。"""

    if values is None:
        return []

    return [value.strip() for value in values if value and value.strip()]


def _load_list(raw_json: str) -> list[str]:
    """从 SQLite JSON 字段恢复列表；坏数据返回空列表。"""

    try:
        values = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(values, list):
        return []

    return [value for value in values if isinstance(value, str)]


def _record_from_row(row) -> InterviewJDRecord:
    """把 sqlite3.Row 转成 InterviewJDRecord。"""

    return InterviewJDRecord(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        role_family=row["role_family"],
        seniority=row["seniority"],
        target_graduation_years=_load_list(row["target_graduation_years_json"]),
        raw_text=row["raw_text"],
        responsibilities=_load_list(row["responsibilities_json"]),
        must_have=_load_list(row["must_have_json"]),
        core_skills=_load_list(row["core_skills_json"]),
        preferred_skills=_load_list(row["preferred_skills_json"]),
        bonus_skills=_load_list(row["bonus_skills_json"]),
        keywords=_load_list(row["keywords_json"]),
        interview_focus=_load_list(row["interview_focus_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
