"""Persistence operations for user-owned custom personas."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import CUSTOM_PERSONAS_TABLE, CustomPersonaRecord


def insert_persona(record: CustomPersonaRecord, *, conn: Connection | None = None) -> CustomPersonaRecord:
    sql = f"""
    INSERT INTO {CUSTOM_PERSONAS_TABLE}
      (id, user_id, name, description, system_prompt, status, created_at, updated_at)
    VALUES (:id, :user_id, :name, :description, :system_prompt, :status, :created_at, :updated_at)
    """
    _run(sql, _params(record), conn=conn)
    return record


def get_persona(persona_id: str, *, user_id: str | None = None, conn: Connection | None = None) -> CustomPersonaRecord | None:
    sql = f"""SELECT id, user_id, name, description, system_prompt, status, created_at, updated_at
              FROM {CUSTOM_PERSONAS_TABLE} WHERE id = :id"""
    params = {"id": persona_id}
    if user_id is not None:
        sql += " AND user_id = :user_id"
        params["user_id"] = user_id
    row = _fetch(sql, params, conn=conn)
    return _from_row(row) if row else None


def list_personas(user_id: str, *, include_disabled: bool = False, conn: Connection | None = None) -> list[CustomPersonaRecord]:
    sql = f"""SELECT id, user_id, name, description, system_prompt, status, created_at, updated_at
              FROM {CUSTOM_PERSONAS_TABLE} WHERE user_id = :user_id"""
    params: dict[str, object] = {"user_id": user_id}
    if not include_disabled:
        sql += " AND status = 'ACTIVE'"
    sql += " ORDER BY updated_at DESC, id DESC"
    rows = _fetch_all(sql, params, conn=conn)
    return [_from_row(row) for row in rows]


def update_persona(record: CustomPersonaRecord, *, conn: Connection | None = None) -> CustomPersonaRecord:
    record.updated_at = datetime.now(timezone.utc).isoformat()
    sql = f"""UPDATE {CUSTOM_PERSONAS_TABLE}
              SET name=:name, description=:description, system_prompt=:system_prompt,
                  status=:status, updated_at=:updated_at WHERE id=:id AND user_id=:user_id"""
    _run(sql, _params(record), conn=conn)
    return record


def _params(record: CustomPersonaRecord) -> dict[str, object]:
    return {field: getattr(record, field) for field in (
        "id", "user_id", "name", "description", "system_prompt", "status", "created_at", "updated_at"
    )}


def _run(sql: str, params: dict[str, object], *, conn: Connection | None) -> None:
    if conn is not None:
        conn.execute(text(sql), params)
    else:
        with get_engine().begin() as connection:
            connection.execute(text(sql), params)


def _fetch(sql: str, params: dict[str, object], *, conn: Connection | None):
    if conn is not None:
        return conn.execute(text(sql), params).mappings().fetchone()
    with get_engine().connect() as connection:
        return connection.execute(text(sql), params).mappings().fetchone()


def _fetch_all(sql: str, params: dict[str, object], *, conn: Connection | None):
    if conn is not None:
        return conn.execute(text(sql), params).mappings().fetchall()
    with get_engine().connect() as connection:
        return connection.execute(text(sql), params).mappings().fetchall()


def _from_row(row) -> CustomPersonaRecord:
    return CustomPersonaRecord(**dict(row))
