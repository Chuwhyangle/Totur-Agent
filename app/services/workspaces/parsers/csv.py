"""CSV parser using the Python standard library."""

import csv
from pathlib import Path

from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.parsers.base import segment_text


def parse_csv(path: Path, *, asset_id: str, media_type: str, settings: WorkspaceAssetSettings) -> ParsedAsset:
    text = path.read_text(encoding="utf-8")
    if len(text) > settings.max_parsed_chars:
        raise ValueError("Parsed CSV exceeds configured limit")
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as source:
        for row_number, row in enumerate(csv.reader(source), start=1):
            row_text = ", ".join(row)
            rows.extend(segment_text(row_text, locator={"row_start": row_number, "row_end": row_number}))
    return ParsedAsset(asset_id, media_type, "csv", "1", tuple(rows))
