"""Workspace Task and Step application service."""

from datetime import datetime, timezone
import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.db.models import TaskAssetRefRecord, WorkspaceTaskRecord, WorkspaceTaskStatus, WorkspaceTaskStepRecord, WorkspaceTaskStepStatus
from app.repositories import workspace_asset_repository as asset_repository
from app.repositories import workspace_task_repository as task_repository
from app.repositories.session_repository import get_session
from app.services.workspaces.workspace_service import WorkspaceService


class WorkspaceTaskError(ValueError):
    error_code = "workspace_task_error"


class TaskNotFoundError(WorkspaceTaskError):
    error_code = "task_not_found"


class TaskStateError(WorkspaceTaskError):
    error_code = "invalid_task_state"


class TaskValidationError(WorkspaceTaskError):
    error_code = "invalid_task"


class TaskService:
    def __init__(self) -> None:
        self.workspace_service = WorkspaceService()

    def create_task(self, *, user_id: str, workspace_id: str, session_id: int, trace_id: str, goal: str, warning_count: int = 0) -> WorkspaceTaskRecord:
        workspace = self.workspace_service.require_active_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        if warning_count < 0:
            raise TaskValidationError("warning_count must not be negative")
        normalized_goal = _normalize_goal(goal)
        session = get_session(session_id)
        if session is None or session.user_id != user_id.strip() or session.workspace_id != workspace.id:
            raise TaskValidationError("session does not belong to Workspace")
        existing = task_repository.get_task_by_trace_id(trace_id)
        if existing:
            if existing.workspace_id != workspace.id:
                raise TaskValidationError("trace_id is already used by another Workspace")
            return existing
        now = _now()
        record = WorkspaceTaskRecord(
            id=str(uuid4()), workspace_id=workspace.id, session_id=session_id, trace_id=trace_id,
            goal=normalized_goal, status=WorkspaceTaskStatus.RUNNING, warning_count=warning_count,
            error_code=None, started_at=now, finished_at=None, created_at=now, updated_at=now,
        )
        try:
            return task_repository.create_task(record)
        except IntegrityError:
            existing = task_repository.get_task_by_trace_id(trace_id)
            if existing:
                return existing
            raise

    def get_owned_task(self, *, user_id: str, workspace_id: str, task_id: str) -> WorkspaceTaskRecord:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        record = task_repository.get_task(task_id)
        if record is None or record.workspace_id != workspace_id:
            raise TaskNotFoundError("Task not found")
        return record

    def list_tasks(self, *, user_id: str, workspace_id: str, limit: int = 50) -> list[WorkspaceTaskRecord]:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        return task_repository.list_workspace_tasks(workspace_id, limit=limit)

    def create_step(self, *, user_id: str, workspace_id: str, task_id: str, tool_call_id: str, step_type: str, tool_name: str, input_summary: str | None = None) -> WorkspaceTaskStepRecord:
        task = self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        existing = task_repository.get_step_by_tool_call_id(task_id, tool_call_id)
        if existing:
            return existing
        if task.status is not WorkspaceTaskStatus.RUNNING:
            raise TaskStateError("Completed tasks cannot receive new steps")
        now = _now()
        record = WorkspaceTaskStepRecord(
            id=0, task_id=task_id, sequence_no=task_repository.next_sequence_no(task_id),
            tool_call_id=tool_call_id, step_type=step_type, tool_name=tool_name,
            status=WorkspaceTaskStepStatus.RUNNING, input_summary=(input_summary or "")[:1000] or None,
            output_summary=None, error_code=None, started_at=now, finished_at=None, created_at=now,
        )
        try:
            return task_repository.create_step(record)
        except IntegrityError:
            existing = task_repository.get_step_by_tool_call_id(task_id, tool_call_id)
            if existing:
                return existing
            raise

    def get_step_by_tool_call_id(self, *, user_id: str, workspace_id: str, task_id: str, tool_call_id: str) -> WorkspaceTaskStepRecord | None:
        self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        return task_repository.get_step_by_tool_call_id(task_id, tool_call_id)

    def complete_step(self, *, user_id: str, workspace_id: str, step_id: int, output_summary: str | None = None) -> WorkspaceTaskStepRecord:
        step = self._owned_step(user_id=user_id, workspace_id=workspace_id, step_id=step_id)
        if not task_repository.complete_step(step_id, output_summary=(output_summary or "")[:1000] or None):
            raise TaskStateError("Step is no longer running")
        return task_repository.get_step(step_id) or step

    def fail_step(self, *, user_id: str, workspace_id: str, step_id: int, error_code: str, output_summary: str | None = None) -> WorkspaceTaskStepRecord:
        step = self._owned_step(user_id=user_id, workspace_id=workspace_id, step_id=step_id)
        if not task_repository.fail_step(step_id, error_code=error_code, output_summary=(output_summary or "")[:1000] or None):
            raise TaskStateError("Step is no longer running")
        return task_repository.get_step(step_id) or step

    def record_asset_ref(self, *, user_id: str, workspace_id: str, task_id: str, asset_id: str, first_step_id: int) -> TaskAssetRefRecord:
        task = self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if task.status is not WorkspaceTaskStatus.RUNNING:
            raise TaskStateError("Completed tasks cannot receive asset references")
        step = task_repository.get_step(first_step_id)
        asset = asset_repository.get_asset(asset_id)
        if step is None or step.task_id != task_id or asset is None or asset.workspace_id != workspace_id:
            raise TaskValidationError("Asset and step must belong to the Task Workspace")
        existing = task_repository.get_asset_ref(task_id, asset_id)
        if existing:
            return existing
        return task_repository.record_asset_ref(TaskAssetRefRecord(task_id=task_id, asset_id=asset_id, first_step_id=first_step_id, created_at=_now()))

    def complete_task(self, *, user_id: str, workspace_id: str, task_id: str) -> WorkspaceTaskRecord:
        task = self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if task.status is WorkspaceTaskStatus.RUNNING and not task_repository.complete_task(task_id):
            raise TaskStateError("Task could not be completed")
        return task_repository.get_task(task_id) or task

    def fail_task(self, *, user_id: str, workspace_id: str, task_id: str, error_code: str) -> WorkspaceTaskRecord:
        task = self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if task.status is WorkspaceTaskStatus.RUNNING and not task_repository.fail_task(task_id, error_code=error_code):
            raise TaskStateError("Task could not be failed")
        return task_repository.get_task(task_id) or task

    def add_warning(self, *, user_id: str, workspace_id: str, task_id: str) -> WorkspaceTaskRecord:
        task = self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if task.status is WorkspaceTaskStatus.RUNNING:
            task_repository.increment_warning_count(task_id)
        return task_repository.get_task(task_id) or task

    def list_steps(self, task_id: str) -> list[WorkspaceTaskStepRecord]:
        return task_repository.list_task_steps(task_id)

    def list_asset_refs(self, task_id: str) -> list[TaskAssetRefRecord]:
        return task_repository.list_task_asset_refs(task_id)

    def _owned_step(self, *, user_id: str, workspace_id: str, step_id: int) -> WorkspaceTaskStepRecord:
        step = task_repository.get_step(step_id)
        if step is None:
            raise TaskNotFoundError("Step not found")
        self.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=step.task_id)
        return step


def _normalize_goal(goal: str) -> str:
    normalized = re.sub(r"\s+", " ", goal.strip())
    if not normalized or len(normalized) > 500:
        raise TaskValidationError("goal must contain 1 to 500 characters")
    return normalized


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
