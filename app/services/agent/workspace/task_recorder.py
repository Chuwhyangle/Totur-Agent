"""Request-scoped adapter from Agent tool calls to Workspace task records."""

from dataclasses import dataclass
import re

from app.db.models import WorkspaceTaskRecord, WorkspaceTaskStepRecord
from app.services.workspaces.task_service import TaskService


@dataclass
class WorkspaceTaskRecorder:
    """Owns one request's lazy Task and current tool Step state."""

    user_id: str
    session_id: int
    workspace_id: str
    trace_id: str
    current_goal: str
    task_service: TaskService | None = None
    task: WorkspaceTaskRecord | None = None
    current_step: WorkspaceTaskStepRecord | None = None

    def __post_init__(self) -> None:
        self.task_service = self.task_service or TaskService()
        self.current_goal = _normalize_goal(self.current_goal)

    @property
    def task_id(self) -> str | None:
        return self.task.id if self.task is not None else None

    @property
    def current_step_id(self) -> int | None:
        return self.current_step.id if self.current_step is not None else None

    def ensure_task(self) -> WorkspaceTaskRecord:
        if self.task is None:
            self.task = self.task_service.create_task(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                session_id=self.session_id,
                trace_id=self.trace_id,
                goal=self.current_goal,
            )
        return self.task

    def start_step(self, *, tool_call_id: str, tool_name: str, input_summary: str | None = None) -> WorkspaceTaskStepRecord:
        task = self.ensure_task()
        self.current_step = self.task_service.create_step(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            task_id=task.id,
            tool_call_id=tool_call_id,
            step_type="workspace_tool",
            tool_name=tool_name,
            input_summary=input_summary,
        )
        return self.current_step

    def finish_step(self, step_id: int, output_summary: str | None = None) -> None:
        self.task_service.complete_step(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            step_id=step_id,
            output_summary=output_summary,
        )
        if self.current_step_id == step_id:
            self.current_step = None

    def fail_step(self, step_id: int, *, error_code: str, output_summary: str | None = None) -> None:
        self.task_service.fail_step(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            step_id=step_id,
            error_code=error_code,
            output_summary=output_summary,
        )
        if self.task_id is not None:
            self.task_service.add_warning(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                task_id=self.task_id,
            )
        if self.current_step_id == step_id:
            self.current_step = None

    def record_asset_ref(self, asset_id: str, *, first_step_id: int | None = None) -> None:
        task = self.ensure_task()
        step_id = first_step_id or self.current_step_id
        if step_id is None:
            raise RuntimeError("workspace_step_required")
        self.task_service.record_asset_ref(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            task_id=task.id,
            asset_id=asset_id,
            first_step_id=step_id,
        )

    def complete_task(self) -> None:
        if self.task_id is None:
            return
        self.task = self.task_service.complete_task(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            task_id=self.task_id,
        )

    def fail_task(self, error_code: str) -> None:
        if self.task_id is None:
            return
        self.task = self.task_service.fail_task(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            task_id=self.task_id,
            error_code=error_code,
        )


def _normalize_goal(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())[:500] or "Workspace task"
