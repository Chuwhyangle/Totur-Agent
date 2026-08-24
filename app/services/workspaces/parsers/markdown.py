"""Markdown parser with heading and line locators."""

import re
from pathlib import Path

from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.parsers.base import segment_text


def parse_markdown(path: Path, *, asset_id: str, media_type: str, settings: WorkspaceAssetSettings) -> ParsedAsset:
    text = path.read_text(encoding="utf-8")
    if len(text) > settings.max_parsed_chars:
        raise ValueError("Parsed Markdown exceeds configured limit")
    lines = text.splitlines(keepends=True)
    segments: list[dict[str, object]] = []
    heading = None
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            heading = match.group(1).strip()
        segments.extend(segment_text(line, locator={"heading": heading, "line_start": line_number, "line_end": line_number}))
    return ParsedAsset(asset_id, media_type, "markdown", "1", tuple(segments))
