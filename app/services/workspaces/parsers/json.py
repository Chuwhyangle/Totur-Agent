"""JSON parser with a compact preview representation."""

import json
from pathlib import Path

from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.parsers.base import segment_text


def parse_json(path: Path, *, asset_id: str, media_type: str, settings: WorkspaceAssetSettings) -> ParsedAsset:
    text = path.read_text(encoding="utf-8")
    if len(text) > settings.max_parsed_chars:
        raise ValueError("Parsed JSON exceeds configured limit")
    value = json.loads(text)
    pretty = json.dumps(value, ensure_ascii=False, indent=2)
    segments = segment_text(pretty, locator={"json_path": "$"})
    return ParsedAsset(asset_id, media_type, "json", "1", tuple(segments))
