"""Workspace Task read API schemas."""

from pydantic import BaseModel

from app.db.models import WorkspaceTaskStatus, WorkspaceTaskStepStatus
from app.schemas.workspace_artifacts import WorkspaceArtifactItem
from app.schemas.workspace_assets import WorkspaceAssetItem


class WorkspaceTaskStepItem(BaseModel):
    id: int
    task_id: str
    sequence_no: int
    tool_call_id: str
    step_type: str
    tool_name: str
    status: WorkspaceTaskStepStatus
    input_summary: str | None
    output_summary: str | None
    error_code: str | None
    started_at: str
    finished_at: str | None
    created_at: str


class WorkspaceTaskItem(BaseModel):
    id: str
    workspace_id: str
    session_id: int
    trace_id: str
    goal: str
    status: WorkspaceTaskStatus
    warning_count: int
    error_code: str | None
    started_at: str
    finished_at: str | None
    created_at: str
    updated_at: str
    steps: list[WorkspaceTaskStepItem] = []
    assets: list[WorkspaceAssetItem] = []
    artifacts: list[WorkspaceArtifactItem] = []


class WorkspaceTaskListResponse(BaseModel):
    items: list[WorkspaceTaskItem]
