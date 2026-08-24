"""Immutable request context passed to Workspace-aware Agent components."""

from dataclasses import dataclass

from app.services.agent.workspace.task_recorder import WorkspaceTaskRecorder


@dataclass(frozen=True)
class AgentExecutionContext:
    user_id: str
    session_id: int
    workspace_id: str | None
    trace_id: str
    current_goal: str
    task_recorder: WorkspaceTaskRecorder | None
