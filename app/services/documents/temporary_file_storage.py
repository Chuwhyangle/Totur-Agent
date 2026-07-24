"""Safe filesystem storage for temporary PDF uploads."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO
from uuid import uuid4


PDF_MIME_TYPE = "application/pdf"
PDF_MAGIC_BYTES = b"%PDF-"


class TemporaryFileStorageError(RuntimeError):
    """Base exception for temporary attachment storage."""


class InvalidAttachmentFilename(TemporaryFileStorageError):
    """The client supplied an unsafe or unsupported filename."""


class UnsupportedAttachmentType(TemporaryFileStorageError):
    """The upload is not recognizable as an allowed PDF upload."""


class AttachmentTooLarge(TemporaryFileStorageError):
    """The streamed upload exceeded the configured byte limit."""


class AttachmentStorageError(TemporaryFileStorageError):
    """The attachment could not be safely stored or removed."""


@dataclass(frozen=True)
class StoredTemporaryFile:
    """Metadata returned after an atomic temporary-file save."""

    storage_key: str
    size_bytes: int
    sha256: str


class TemporaryFileStorage:
    """Store files under one injected root using random relative keys."""

    def __init__(self, root_path: Path | str, write_chunk_bytes: int) -> None:
        if write_chunk_bytes <= 0:
            raise ValueError("write_chunk_bytes must be positive")
        self.root_path = Path(root_path).expanduser().resolve(strict=False)
        self.write_chunk_bytes = write_chunk_bytes

    def store_pdf(
        self,
        file_stream: BinaryIO,
        original_filename: str,
        max_bytes: int,
        mime_type: str = PDF_MIME_TYPE,
    ) -> StoredTemporaryFile:
        """Stream one recognizable PDF upload to an atomic random path."""

        self._validate_original_filename(original_filename)
        if mime_type.strip().lower() != PDF_MIME_TYPE:
            raise UnsupportedAttachmentType(
                "The upload is not a recognizable PDF upload"
            )
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        storage_key = f"{uuid4().hex}.pdf"
        final_path = self.resolve(storage_key)
        part_path = final_path.with_name(f"{final_path.name}.part")
        size_bytes = 0
        digest = hashlib.sha256()
        leading_bytes = bytearray()

        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
            with part_path.open("xb") as output:
                while True:
                    chunk = file_stream.read(self.write_chunk_bytes)
                    if chunk is None or not isinstance(chunk, (bytes, bytearray)):
                        raise AttachmentStorageError(
                            "The upload stream did not return bytes"
                        )
                    if not chunk:
                        break

                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise AttachmentTooLarge(
                            f"The attachment exceeds the {max_bytes}-byte limit"
                        )

                    if len(leading_bytes) < len(PDF_MAGIC_BYTES):
                        needed = len(PDF_MAGIC_BYTES) - len(leading_bytes)
                        leading_bytes.extend(chunk[:needed])

                    output.write(chunk)
                    digest.update(chunk)

                if size_bytes == 0 or bytes(leading_bytes) != PDF_MAGIC_BYTES:
                    raise UnsupportedAttachmentType(
                        "The upload is not a recognizable PDF upload"
                    )

                output.flush()
                os.fsync(output.fileno())

            os.replace(part_path, final_path)
            return StoredTemporaryFile(
                storage_key=storage_key,
                size_bytes=size_bytes,
                sha256=digest.hexdigest(),
            )
        except (
            InvalidAttachmentFilename,
            UnsupportedAttachmentType,
            AttachmentTooLarge,
            AttachmentStorageError,
        ):
            raise
        except Exception as exc:
            raise AttachmentStorageError(
                "The attachment could not be stored"
            ) from exc
        finally:
            if part_path.exists():
                try:
                    part_path.unlink()
                except OSError as exc:
                    raise AttachmentStorageError(
                        "The temporary upload could not be cleaned up"
                    ) from exc

    def delete(self, storage_key: str) -> None:
        """Idempotently delete one file addressed by an internal storage key."""

        path = self.resolve(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise AttachmentStorageError(
                "The attachment file could not be deleted"
            ) from exc

    def exists(self, storage_key: str) -> bool:
        """Return whether an internal storage key currently exists."""

        return self.resolve(storage_key).is_file()

    def resolve(self, storage_key: str) -> Path:
        """Resolve an internal key while rejecting all root-path escapes."""

        if not storage_key or not storage_key.strip() or "\x00" in storage_key:
            raise AttachmentStorageError("Invalid attachment storage key")
        if "\\" in storage_key:
            raise AttachmentStorageError("Invalid attachment storage key")

        posix_key = PurePosixPath(storage_key)
        windows_key = PureWindowsPath(storage_key)
        if (
            posix_key.is_absolute()
            or windows_key.is_absolute()
            or bool(windows_key.drive)
            or any(part in {".", "..", ""} for part in posix_key.parts)
        ):
            raise AttachmentStorageError("Invalid attachment storage key")

        resolved = (self.root_path / Path(*posix_key.parts)).resolve(strict=False)
        try:
            resolved.relative_to(self.root_path)
        except ValueError as exc:
            raise AttachmentStorageError(
                "Attachment storage key escapes the configured root"
            ) from exc
        return resolved

    @staticmethod
    def _validate_original_filename(original_filename: str) -> None:
        if not original_filename or not original_filename.strip():
            raise InvalidAttachmentFilename(
                "The attachment filename must not be empty"
            )

        filename = original_filename.strip()
        windows_path = PureWindowsPath(filename)
        if (
            "\x00" in filename
            or "/" in filename
            or "\\" in filename
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or filename in {".", ".."}
        ):
            raise InvalidAttachmentFilename(
                "The attachment filename is not allowed"
            )
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedAttachmentType(
                "Only .pdf attachments are supported"
            )
