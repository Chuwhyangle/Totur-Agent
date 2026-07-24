"""Validated runtime settings for temporary conversation attachments."""

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import os

from dotenv import load_dotenv


DEFAULT_TEMP_DOCUMENT_ROOT = "runtime_data/attachments"
DEFAULT_TEMP_DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_TEMP_DOCUMENT_TTL_HOURS = 24
DEFAULT_TEMP_DOCUMENT_MAX_FILES_PER_SESSION = 5
DEFAULT_TEMP_DOCUMENT_WRITE_CHUNK_BYTES = 64 * 1024

_MIN_MAX_BYTES = 1024
_MAX_MAX_BYTES = 100 * 1024 * 1024
_MIN_TTL_HOURS = 1
_MAX_TTL_HOURS = 24 * 30
_MIN_FILES_PER_SESSION = 1
_MAX_FILES_PER_SESSION = 100
_MIN_WRITE_CHUNK_BYTES = 1024
_MAX_WRITE_CHUNK_BYTES = 1024 * 1024


class InvalidTemporaryDocumentSettings(ValueError):
    """Temporary document settings contain an unsafe or invalid value."""


@dataclass(frozen=True)
class TemporaryDocumentSettings:
    """Validated settings injected into temporary document services."""

    root_path: Path
    max_bytes: int = DEFAULT_TEMP_DOCUMENT_MAX_BYTES
    ttl_hours: int = DEFAULT_TEMP_DOCUMENT_TTL_HOURS
    max_files_per_session: int = DEFAULT_TEMP_DOCUMENT_MAX_FILES_PER_SESSION
    write_chunk_bytes: int = DEFAULT_TEMP_DOCUMENT_WRITE_CHUNK_BYTES

    def __post_init__(self) -> None:
        root_path = Path(self.root_path).expanduser().resolve(strict=False)
        object.__setattr__(self, "root_path", root_path)

        _validate_range(
            "TEMP_DOCUMENT_MAX_BYTES",
            self.max_bytes,
            _MIN_MAX_BYTES,
            _MAX_MAX_BYTES,
        )
        _validate_range(
            "TEMP_DOCUMENT_TTL_HOURS",
            self.ttl_hours,
            _MIN_TTL_HOURS,
            _MAX_TTL_HOURS,
        )
        _validate_range(
            "TEMP_DOCUMENT_MAX_FILES_PER_SESSION",
            self.max_files_per_session,
            _MIN_FILES_PER_SESSION,
            _MAX_FILES_PER_SESSION,
        )
        _validate_range(
            "TEMP_DOCUMENT_WRITE_CHUNK_BYTES",
            self.write_chunk_bytes,
            _MIN_WRITE_CHUNK_BYTES,
            _MAX_WRITE_CHUNK_BYTES,
        )


def load_temporary_document_settings(
    environment: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> TemporaryDocumentSettings:
    """Load settings without creating the configured storage directory."""

    if environment is None:
        load_dotenv()
        environment = os.environ

    base_path = (
        Path(project_root).expanduser().resolve(strict=False)
        if project_root is not None
        else Path(__file__).resolve().parents[3]
    )
    raw_root = environment.get(
        "TEMP_DOCUMENT_ROOT",
        DEFAULT_TEMP_DOCUMENT_ROOT,
    ).strip()
    if not raw_root:
        raise InvalidTemporaryDocumentSettings(
            "TEMP_DOCUMENT_ROOT must not be empty"
        )

    root_path = Path(raw_root).expanduser()
    if not root_path.is_absolute():
        root_path = base_path / root_path

    return TemporaryDocumentSettings(
        root_path=root_path,
        max_bytes=_read_integer(
            environment,
            "TEMP_DOCUMENT_MAX_BYTES",
            DEFAULT_TEMP_DOCUMENT_MAX_BYTES,
        ),
        ttl_hours=_read_integer(
            environment,
            "TEMP_DOCUMENT_TTL_HOURS",
            DEFAULT_TEMP_DOCUMENT_TTL_HOURS,
        ),
        max_files_per_session=_read_integer(
            environment,
            "TEMP_DOCUMENT_MAX_FILES_PER_SESSION",
            DEFAULT_TEMP_DOCUMENT_MAX_FILES_PER_SESSION,
        ),
        write_chunk_bytes=_read_integer(
            environment,
            "TEMP_DOCUMENT_WRITE_CHUNK_BYTES",
            DEFAULT_TEMP_DOCUMENT_WRITE_CHUNK_BYTES,
        ),
    )


def _read_integer(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    raw_value = environment.get(name, str(default)).strip()
    try:
        return int(raw_value)
    except ValueError as exc:
        raise InvalidTemporaryDocumentSettings(
            f"{name} must be an integer"
        ) from exc


def _validate_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidTemporaryDocumentSettings(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise InvalidTemporaryDocumentSettings(
            f"{name} must be between {minimum} and {maximum}"
        )
