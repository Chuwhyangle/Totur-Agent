"""Parser dispatch and shared text segmentation."""

from pathlib import Path

from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset


def parse_asset(
    path: Path,
    *,
    asset_id: str,
    media_type: str,
    original_filename: str,
    settings: WorkspaceAssetSettings,
) -> ParsedAsset:
    # Imports stay local so each parser can reuse segment_text without a cycle.
    if media_type == "application/pdf":
        from app.services.workspaces.parsers.pdf import parse_pdf

        return parse_pdf(path, asset_id=asset_id, media_type=media_type, original_filename=original_filename, settings=settings)
    if media_type == "text/markdown":
        from app.services.workspaces.parsers.markdown import parse_markdown

        return parse_markdown(path, asset_id=asset_id, media_type=media_type, settings=settings)
    if media_type == "text/plain":
        from app.services.workspaces.parsers.text import parse_text

        return parse_text(path, asset_id=asset_id, media_type=media_type, settings=settings)
    if media_type == "text/csv":
        from app.services.workspaces.parsers.csv import parse_csv

        return parse_csv(path, asset_id=asset_id, media_type=media_type, settings=settings)
    if media_type == "application/json":
        from app.services.workspaces.parsers.json import parse_json

        return parse_json(path, asset_id=asset_id, media_type=media_type, settings=settings)
    raise ValueError("Unsupported Workspace asset MIME type")


def segment_text(text: str, *, locator: dict[str, object], max_chars: int = 2000) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    if not text:
        return segments
    for start in range(0, len(text), max_chars):
        piece = text[start : start + max_chars]
        segments.append({"segment_id": f"s{len(segments) + 1:06d}", "locator": dict(locator), "text": piece})
    return segments
