"""Deterministic keyword search across parsed Workspace Assets."""

from typing import Any

from app.repositories import workspace_asset_repository
from app.services.agent.tools.workspace_common import get_ready_asset, read_parsed_asset, require_workspace_context


SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_workspace_assets",
        "description": "Search READY Workspace Assets by deterministic keyword matching.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "asset_ids": {"type": "array", "items": {"type": "string"}, "default": []},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def search_workspace_assets(*, execution_context, query: str, asset_ids: list[str] | None = None, limit: int = 10, **_: Any) -> dict[str, Any]:
    context = require_workspace_context(execution_context)
    normalized_query = query.strip().casefold()
    if not normalized_query:
        raise ValueError("query must not be blank")
    limit = min(max(int(limit), 1), 20)
    if asset_ids:
        records = []
        for asset_id in dict.fromkeys(asset_ids):
            records.append(get_ready_asset(context, asset_id))
    else:
        records = workspace_asset_repository.list_workspace_assets(context.workspace_id, status="READY", limit=50)

    hits = []
    for asset_index, asset in enumerate(records):
        payload = read_parsed_asset(asset)
        segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
        filename_count = asset.original_filename.casefold().count(normalized_query)
        for segment_index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text") or "")
            match_count = filename_count + text.casefold().count(normalized_query)
            if match_count <= 0:
                continue
            position = text.casefold().find(normalized_query)
            start = max(0, position - 120) if position >= 0 else 0
            hits.append({
                "asset_id": asset.id,
                "filename": asset.original_filename,
                "segment_id": segment.get("segment_id"),
                "locator": segment.get("locator", {}),
                "snippet": text[start : start + 500],
                "match_count": match_count,
                "_filename_hit": bool(filename_count),
                "_asset_index": asset_index,
                "_segment_index": segment_index,
            })

    hits.sort(key=lambda item: (-int(item["_filename_hit"]), -item["match_count"], item["_asset_index"], item["_segment_index"]))
    visible_hits = []
    for hit in hits[:limit]:
        visible_hits.append({key: value for key, value in hit.items() if not key.startswith("_")})
        if context.task_recorder is not None:
            context.task_recorder.record_asset_ref(hit["asset_id"])
    return {"ok": True, "items": visible_hits, "summary": {"returned_count": len(visible_hits)}}
