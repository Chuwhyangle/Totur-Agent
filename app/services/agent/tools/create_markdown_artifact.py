"""Create a Markdown Artifact using the request's Task and Step."""

from typing import Any

from app.services.agent.tools.workspace_common import require_workspace_context
from app.services.workspaces.artifact_service import ArtifactService


SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_markdown_artifact",
        "description": "Create a Markdown report in the current Workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "markdown_content": {"type": "string", "description": "Markdown report content, maximum 256 KB."},
                "source_asset_ids": {"type": "array", "items": {"type": "string"}, "default": []},
                "supersedes_artifact_id": {"type": ["string", "null"], "default": None},
            },
            "required": ["title", "markdown_content"],
            "additionalProperties": False,
        },
    },
}


def create_markdown_artifact(*, execution_context, tool_call_id: str, title: str, markdown_content: str, source_asset_ids: list[str] | None = None, supersedes_artifact_id: str | None = None, **_: Any) -> dict[str, Any]:
    context = require_workspace_context(execution_context)
    recorder = context.task_recorder
    if recorder is None or recorder.task_id is None or recorder.current_step_id is None:
        raise RuntimeError("workspace_task_required")
    source_ids = list(dict.fromkeys(source_asset_ids or []))
    artifact = ArtifactService().create_artifact(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        task_id=recorder.task_id,
        created_by_step_id=recorder.current_step_id,
        tool_call_id=tool_call_id,
        title=title,
        content=markdown_content,
        source_asset_ids=source_ids,
        supersedes_artifact_id=supersedes_artifact_id,
    )
    for asset_id in source_ids:
        recorder.record_asset_ref(asset_id)
    return {
        "ok": True,
        "artifact_id": artifact.id,
        "title": artifact.title,
        "version_number": artifact.version_number,
        "status": artifact.status.value,
        "content_url": f"/workspaces/{context.workspace_id}/artifacts/{artifact.id}/content",
        "download_url": f"/workspaces/{context.workspace_id}/artifacts/{artifact.id}/download",
    }
