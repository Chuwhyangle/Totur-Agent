"""List metadata for Assets in the current Workspace."""

from typing import Any

from app.services.agent.tools.workspace_common import public_asset, require_workspace_context


SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_workspace_assets",
        "description": "List files in the current Workspace. Returns metadata only.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": ["string", "null"], "enum": ["READY", "PROCESSING", "FAILED", None]},
                "media_type": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
            "additionalProperties": False,
        },
    },
}


def list_workspace_assets(*, execution_context, status: str | None = None, media_type: str | None = None, limit: int = 20, **_: Any) -> dict[str, Any]:
    from app.repositories import workspace_asset_repository

    context = require_workspace_context(execution_context)
    limit = min(max(int(limit), 1), 50)
    normalized_status = status.strip().upper() if isinstance(status, str) and status.strip() else None
    records = workspace_asset_repository.list_workspace_assets(
        context.workspace_id,
        status=normalized_status,
        media_type=media_type.strip().lower() if isinstance(media_type, str) and media_type.strip() else None,
        limit=limit,
    )
    return {"ok": True, "items": [public_asset(record) for record in records], "summary": {"returned_count": len(records)}}
