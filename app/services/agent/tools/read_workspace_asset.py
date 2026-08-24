"""Read bounded parsed segments from a READY Workspace Asset."""

from typing import Any

from app.services.agent.tools.workspace_common import get_ready_asset, read_parsed_asset


SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_workspace_asset",
        "description": "Read a bounded range of parsed segments from a READY Workspace Asset.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "start_segment": {"type": "integer", "minimum": 0, "default": 0},
                "segment_count": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            },
            "required": ["asset_id"],
            "additionalProperties": False,
        },
    },
}


def read_workspace_asset(*, execution_context, asset_id: str, start_segment: int = 0, segment_count: int = 10, **_: Any) -> dict[str, Any]:
    asset = get_ready_asset(execution_context, asset_id)
    if start_segment < 0:
        raise ValueError("start_segment must not be negative")
    segment_count = min(max(int(segment_count), 1), 20)
    payload = read_parsed_asset(asset)
    all_segments = payload.get("segments")
    if not isinstance(all_segments, list):
        raise ValueError("parsed segments are invalid")
    selected = []
    total_chars = 0
    for segment in all_segments[start_segment : start_segment + segment_count]:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "")
        if total_chars + len(text) > 20_000:
            break
        selected.append(segment)
        total_chars += len(text)
    if execution_context.task_recorder is not None:
        execution_context.task_recorder.record_asset_ref(asset.id)
    next_segment = start_segment + len(selected)
    return {
        "ok": True,
        "asset_id": asset.id,
        "filename": asset.original_filename,
        "segments": selected,
        "has_more": next_segment < len(all_segments),
        "next_segment": next_segment if next_segment < len(all_segments) else None,
    }
