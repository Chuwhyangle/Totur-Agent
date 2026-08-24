"""UTF-8 plain text parser."""

from pathlib import Path

from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.parsers.base import segment_text


def parse_text(path: Path, *, asset_id: str, media_type: str, settings: WorkspaceAssetSettings) -> ParsedAsset:
    text = path.read_text(encoding="utf-8")
    if len(text) > settings.max_parsed_chars:
        raise ValueError("Parsed text exceeds configured limit")
    lines = text.splitlines(keepends=True)
    segments = []
    for line_number, line in enumerate(lines, start=1):
        segments.extend(segment_text(line, locator={"line_start": line_number, "line_end": line_number}))
    if not segments and text:
        segments = segment_text(text, locator={"line_start": 1, "line_end": 1})
    return ParsedAsset(asset_id, media_type, "text", "1", tuple(segments))
