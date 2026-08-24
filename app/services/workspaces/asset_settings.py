"""Validated runtime settings for Workspace asset storage."""

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_WORKSPACE_ROOT = "runtime_data/workspaces"
DEFAULT_ASSET_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_ASSET_MAX_FILES = 100
DEFAULT_ASSET_WRITE_CHUNK_BYTES = 64 * 1024
DEFAULT_ASSET_MAX_PARSED_CHARS = 2_000_000
DEFAULT_ASSET_MAX_PDF_PAGES = 300
DEFAULT_ASSET_PROCESSING_STALE_SECONDS = 600
DEFAULT_ASSET_RECOVERY_BATCH_SIZE = 50


class InvalidWorkspaceAssetSettings(ValueError):
    """Workspace asset settings are missing or outside safe bounds."""


@dataclass(frozen=True)
class WorkspaceAssetSettings:
    root_path: Path
    max_bytes: int
    max_files: int
    write_chunk_bytes: int
    max_parsed_chars: int
    max_pdf_pages: int
    processing_stale_seconds: int
    recovery_batch_size: int

    def __post_init__(self) -> None:
        checks = (
            ("WORKSPACE_ASSET_MAX_BYTES", self.max_bytes, 1024, 100 * 1024 * 1024),
            ("WORKSPACE_ASSET_MAX_FILES", self.max_files, 1, 10_000),
            ("WORKSPACE_ASSET_WRITE_CHUNK_BYTES", self.write_chunk_bytes, 1024, 4 * 1024 * 1024),
            ("WORKSPACE_ASSET_MAX_PARSED_CHARS", self.max_parsed_chars, 1_000, 20_000_000),
            ("WORKSPACE_ASSET_MAX_PDF_PAGES", self.max_pdf_pages, 1, 10_000),
            ("WORKSPACE_ASSET_PROCESSING_STALE_SECONDS", self.processing_stale_seconds, 30, 7 * 24 * 3600),
            ("WORKSPACE_ASSET_RECOVERY_BATCH_SIZE", self.recovery_batch_size, 1, 1_000),
        )
        for name, value, minimum, maximum in checks:
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidWorkspaceAssetSettings(f"{name} must be an integer")
            if value < minimum or value > maximum:
                raise InvalidWorkspaceAssetSettings(
                    f"{name} must be between {minimum} and {maximum}"
                )


def load_workspace_asset_settings(
    environment: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> WorkspaceAssetSettings:
    """Load settings without creating directories."""

    if environment is None:
        load_dotenv()
        environment = os.environ
    base_path = (
        Path(project_root).expanduser().resolve(strict=False)
        if project_root is not None
        else Path(__file__).resolve().parents[3]
    )
    raw_root = environment.get("WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT).strip()
    if not raw_root:
        raise InvalidWorkspaceAssetSettings("WORKSPACE_ROOT must not be empty")
    root_path = Path(raw_root).expanduser()
    if not root_path.is_absolute():
        root_path = base_path / root_path
    return WorkspaceAssetSettings(
        root_path=root_path.resolve(strict=False),
        max_bytes=_read_int(environment, "WORKSPACE_ASSET_MAX_BYTES", DEFAULT_ASSET_MAX_BYTES),
        max_files=_read_int(environment, "WORKSPACE_ASSET_MAX_FILES", DEFAULT_ASSET_MAX_FILES),
        write_chunk_bytes=_read_int(environment, "WORKSPACE_ASSET_WRITE_CHUNK_BYTES", DEFAULT_ASSET_WRITE_CHUNK_BYTES),
        max_parsed_chars=_read_int(environment, "WORKSPACE_ASSET_MAX_PARSED_CHARS", DEFAULT_ASSET_MAX_PARSED_CHARS),
        max_pdf_pages=_read_int(environment, "WORKSPACE_ASSET_MAX_PDF_PAGES", DEFAULT_ASSET_MAX_PDF_PAGES),
        processing_stale_seconds=_read_int(environment, "WORKSPACE_ASSET_PROCESSING_STALE_SECONDS", DEFAULT_ASSET_PROCESSING_STALE_SECONDS),
        recovery_batch_size=_read_int(environment, "WORKSPACE_ASSET_RECOVERY_BATCH_SIZE", DEFAULT_ASSET_RECOVERY_BATCH_SIZE),
    )


def _read_int(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidWorkspaceAssetSettings(f"{name} must be an integer") from exc
