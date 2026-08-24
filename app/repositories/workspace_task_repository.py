"""Database operations for Workspace Tasks, Steps, and Asset references."""

from datetime import datetime, timezone

from sqlalchemy import Connection, text

from app.db.engine import get_engine
from app.db.models import (
    TASK_ASSET_REFS_TABLE,
    TASK_STEPS_TABLE,
    TASKS_TABLE,
    TaskAssetRefRecord,
    WorkspaceTaskRecord,
    WorkspaceTaskStatus,
    WorkspaceTaskStepRecord,
)


_TASK_COLUMNS = "id, workspace_id, session_id, trace_id, goal, status, warning_count, error_code, started_at, finished_at, created_at, updated_at"
_STEP_COLUMNS = "id, task_id, sequence_no, tool_call_id, step_type, tool_name, status, input_summary, output_summary, error_code, started_at, finished_at, created_at"


def create_task(record: WorkspaceTaskRecord, *, conn: Connection | None = None) -> WorkspaceTaskRecord:
    _execute(
        f"""INSERT INTO {TASKS_TABLE} ({_TASK_COLUMNS}) VALUES
        (:id, :workspace_id, :session_id, :trace_id, :goal, :status, :warning_count, :error_code, :started_at, :finished_at, :created_at, :updated_at)""",
        _task_params(record), conn=conn, write=True,
    )
    return record


def get_task(task_id: str, *, conn: Connection | None = None) -> WorkspaceTaskRecord | None:
    row = _fetch_one(f"SELECT {_TASK_COLUMNS} FROM {TASKS_TABLE} WHERE id = :id", {"id": task_id}, conn=conn)
    return _task_from_row(row) if row else None


def get_task_by_trace_id(trace_id: str, *, conn: Connection | None = None) -> WorkspaceTaskRecord | None:
    row = _fetch_one(f"SELECT {_TASK_COLUMNS} FROM {TASKS_TABLE} WHERE trace_id = :trace_id", {"trace_id": trace_id}, conn=conn)
    return _task_from_row(row) if row else None


def list_workspace_tasks(workspace_id: str, *, limit: int = 50, conn: Connection | None = None) -> list[WorkspaceTaskRecord]:
    rows = _fetch_all(f"SELECT {_TASK_COLUMNS} FROM {TASKS_TABLE} WHERE workspace_id = :workspace_id ORDER BY created_at DESC, id DESC LIMIT :limit", {"workspace_id": workspace_id, "limit": limit}, conn=conn)
    return [_task_from_row(row) for row in rows]


def create_step(record: WorkspaceTaskStepRecord, *, conn: Connection | None = None) -> WorkspaceTaskStepRecord:
    _execute(
        f"""INSERT INTO {TASK_STEPS_TABLE} (task_id, sequence_no, tool_call_id, step_type, tool_name, status, input_summary, output_summary, error_code, started_at, finished_at, created_at)
        VALUES (:task_id, :sequence_no, :tool_call_id, :step_type, :tool_name, :status, :input_summary, :output_summary, :error_code, :started_at, :finished_at, :created_at)""",
        {"task_id": record.task_id, "sequence_no": record.sequence_no, "tool_call_id": record.tool_call_id, "step_type": record.step_type, "tool_name": record.tool_name, "status": record.status.value, "input_summary": record.input_summary, "output_summary": record.output_summary, "error_code": record.error_code, "started_at": record.started_at, "finished_at": record.finished_at, "created_at": record.created_at},
        conn=conn, write=True,
    )
    row = _fetch_one(f"SELECT {_STEP_COLUMNS} FROM {TASK_STEPS_TABLE} WHERE task_id = :task_id AND tool_call_id = :tool_call_id", {"task_id": record.task_id, "tool_call_id": record.tool_call_id}, conn=conn)
    return _step_from_row(row) if row else record


def get_step_by_tool_call_id(task_id: str, tool_call_id: str, *, conn: Connection | None = None) -> WorkspaceTaskStepRecord | None:
    row = _fetch_one(f"SELECT {_STEP_COLUMNS} FROM {TASK_STEPS_TABLE} WHERE task_id = :task_id AND tool_call_id = :tool_call_id", {"task_id": task_id, "tool_call_id": tool_call_id}, conn=conn)
    return _step_from_row(row) if row else None


def get_step(step_id: int, *, conn: Connection | None = None) -> WorkspaceTaskStepRecord | None:
    row = _fetch_one(f"SELECT {_STEP_COLUMNS} FROM {TASK_STEPS_TABLE} WHERE id = :id", {"id": step_id}, conn=conn)
    return _step_from_row(row) if row else None


def next_sequence_no(task_id: str, *, conn: Connection | None = None) -> int:
    row = _fetch_one(f"SELECT COALESCE(MAX(sequence_no), 0) + 1 AS next_sequence FROM {TASK_STEPS_TABLE} WHERE task_id = :task_id", {"task_id": task_id}, conn=conn)
    return int(row["next_sequence"]) if row else 1


def complete_step(step_id: int, *, output_summary: str | None = None, conn: Connection | None = None) -> bool:
    return _finish_step(step_id, "SUCCEEDED", output_summary=output_summary, error_code=None, conn=conn)


def fail_step(step_id: int, *, error_code: str, output_summary: str | None = None, conn: Connection | None = None) -> bool:
    return _finish_step(step_id, "FAILED", output_summary=output_summary, error_code=error_code, conn=conn)


def record_asset_ref(record: TaskAssetRefRecord, *, conn: Connection | None = None) -> TaskAssetRefRecord:
    existing = get_asset_ref(record.task_id, record.asset_id, conn=conn)
    if existing:
        return existing
    _execute(
        f"INSERT INTO {TASK_ASSET_REFS_TABLE} (task_id, asset_id, first_step_id, created_at) VALUES (:task_id, :asset_id, :first_step_id, :created_at)",
        {"task_id": record.task_id, "asset_id": record.asset_id, "first_step_id": record.first_step_id, "created_at": record.created_at}, conn=conn, write=True,
    )
    return record


def get_asset_ref(task_id: str, asset_id: str, *, conn: Connection | None = None) -> TaskAssetRefRecord | None:
    row = _fetch_one(f"SELECT task_id, asset_id, first_step_id, created_at FROM {TASK_ASSET_REFS_TABLE} WHERE task_id = :task_id AND asset_id = :asset_id", {"task_id": task_id, "asset_id": asset_id}, conn=conn)
    return TaskAssetRefRecord(**dict(row)) if row else None


def complete_task(task_id: str, *, conn: Connection | None = None) -> bool:
    return _finish_task(task_id, "COMPLETED", None, conn=conn)


def fail_task(task_id: str, *, error_code: str, conn: Connection | None = None) -> bool:
    return _finish_task(task_id, "FAILED", error_code, conn=conn)


def list_task_steps(task_id: str, *, conn: Connection | None = None) -> list[WorkspaceTaskStepRecord]:
    rows = _fetch_all(f"SELECT {_STEP_COLUMNS} FROM {TASK_STEPS_TABLE} WHERE task_id = :task_id ORDER BY sequence_no", {"task_id": task_id}, conn=conn)
    return [_step_from_row(row) for row in rows]


def list_task_asset_refs(task_id: str, *, conn: Connection | None = None) -> list[TaskAssetRefRecord]:
    rows = _fetch_all(f"SELECT task_id, asset_id, first_step_id, created_at FROM {TASK_ASSET_REFS_TABLE} WHERE task_id = :task_id ORDER BY created_at, asset_id", {"task_id": task_id}, conn=conn)
    return [TaskAssetRefRecord(**dict(row)) for row in rows]


def _finish_step(step_id: int, status: str, *, output_summary: str | None, error_code: str | None, conn: Connection | None) -> bool:
    result = _execute(
        f"UPDATE {TASK_STEPS_TABLE} SET status = :status, output_summary = :output_summary, error_code = :error_code, finished_at = :finished_at WHERE id = :id AND status = 'RUNNING'",
        {"id": step_id, "status": status, "output_summary": output_summary, "error_code": error_code, "finished_at": _now()}, conn=conn, write=True,
    )
    return result.rowcount == 1


def _finish_task(task_id: str, status: str, error_code: str | None, *, conn: Connection | None) -> bool:
    result = _execute(
        f"UPDATE {TASKS_TABLE} SET status = :status, error_code = :error_code, finished_at = :finished_at, updated_at = :updated_at WHERE id = :id AND status = 'RUNNING'",
        {"id": task_id, "status": status, "error_code": error_code, "finished_at": _now(), "updated_at": _now()}, conn=conn, write=True,
    )
    return result.rowcount == 1


def _task_params(record: WorkspaceTaskRecord) -> dict[str, object]:
    return {"id": record.id, "workspace_id": record.workspace_id, "session_id": record.session_id, "trace_id": record.trace_id, "goal": record.goal, "status": record.status.value, "warning_count": record.warning_count, "error_code": record.error_code, "started_at": record.started_at, "finished_at": record.finished_at, "created_at": record.created_at, "updated_at": record.updated_at}


def _task_from_row(row) -> WorkspaceTaskRecord:
    return WorkspaceTaskRecord(**dict(row))


def _step_from_row(row) -> WorkspaceTaskStepRecord:
    return WorkspaceTaskStepRecord(**dict(row))


def _execute(sql: str, params: dict[str, object], *, conn: Connection | None, write: bool):
    if conn is not None:
        return conn.execute(text(sql), params)
    context = get_engine().begin() if write else get_engine().connect()
    with context as connection:
        return connection.execute(text(sql), params)


def _fetch_one(sql: str, params: dict[str, object], *, conn: Connection | None):
    return _execute(sql, params, conn=conn, write=False).mappings().fetchone()


def _fetch_all(sql: str, params: dict[str, object], *, conn: Connection | None):
    return _execute(sql, params, conn=conn, write=False).mappings().fetchall()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
