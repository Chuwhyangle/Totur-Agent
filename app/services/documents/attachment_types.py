"""Allowed temporary attachment formats and their upload constraints."""

from pathlib import Path, PureWindowsPath


TEXT_LIKE_EXTENSIONS = {
    ".txt",
    ".log",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".html",
    ".xml",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".sql",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".css",
}

TEXT_LIKE_MAX_BYTES = 2 * 1024 * 1024
DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
SPREADSHEET_MAX_BYTES = 10 * 1024 * 1024

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".html": "text/html",
    ".xml": "application/xml",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".jsx": "text/jsx",
    ".ts": "text/typescript",
    ".tsx": "text/tsx",
    ".java": "text/x-java-source",
    ".go": "text/x-go",
    ".rs": "text/x-rust",
    ".c": "text/x-c",
    ".cpp": "text/x-c++",
    ".h": "text/x-c",
    ".cs": "text/plain",
    ".sql": "application/sql",
    ".sh": "application/x-sh",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".ini": "text/plain",
    ".css": "text/css",
}

LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}
ARCHIVE_EXTENSIONS = {".zip", ".rar"}


class AttachmentTypeValidationError(ValueError):
    """Base error raised while validating attachment metadata."""


class InvalidAttachmentFilenameError(AttachmentTypeValidationError):
    """The supplied filename is not a single safe filename."""


class UnsupportedAttachmentTypeError(AttachmentTypeValidationError):
    """The extension and MIME type do not describe an allowed attachment."""


class LegacyOfficeAttachmentError(AttachmentTypeValidationError):
    """Legacy binary Office files require conversion before upload."""


class ArchiveAttachmentNotSupportedError(AttachmentTypeValidationError):
    """Archives are intentionally not accepted as attachments."""


def validate_filename_and_media_type(filename: str, media_type: str) -> str:
    """Return a supported extension after strict filename and MIME checks."""

    if not filename or not filename.strip() or "\x00" in filename:
        raise InvalidAttachmentFilenameError("Attachment filename is invalid")

    name = filename.strip()
    windows_path = PureWindowsPath(name)
    if (
        "/" in name
        or "\\" in name
        or name in {".", ".."}
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        raise InvalidAttachmentFilenameError(
            "Attachment filename must be a single file name"
        )

    extension = Path(name).suffix.lower()
    if extension in LEGACY_OFFICE_EXTENSIONS:
        raise LegacyOfficeAttachmentError(
            "Legacy Office files must be converted before upload"
        )
    if extension in ARCHIVE_EXTENSIONS:
        raise ArchiveAttachmentNotSupportedError("Archives are not supported")

    expected_media_type = MEDIA_TYPES.get(extension)
    if expected_media_type is None:
        raise UnsupportedAttachmentTypeError("Unsupported attachment type")
    if media_type.strip().lower() != expected_media_type:
        raise UnsupportedAttachmentTypeError("Filename and MIME type do not match")
    return extension


def max_bytes_for_extension(extension: str) -> int:
    """Return the per-type upload ceiling for one already-validated extension."""

    if extension in TEXT_LIKE_EXTENSIONS:
        return TEXT_LIKE_MAX_BYTES
    if extension == ".xlsx":
        return SPREADSHEET_MAX_BYTES
    if extension in {".pdf", ".docx", ".pptx"}:
        return DOCUMENT_MAX_BYTES
    raise ValueError(f"Unsupported attachment extension: {extension}")
