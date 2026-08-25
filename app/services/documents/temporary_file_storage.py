"""Safe filesystem storage for temporary conversation attachments."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from app.services.documents.attachment_types import (
    ArchiveAttachmentNotSupportedError,
    InvalidAttachmentFilenameError,
    LegacyOfficeAttachmentError,
    TEXT_LIKE_EXTENSIONS,
    UnsupportedAttachmentTypeError,
    max_bytes_for_extension,
    validate_filename_and_media_type,
)


PDF_MIME_TYPE = "application/pdf"
PDF_MAGIC_BYTES = b"%PDF-"


class TemporaryFileStorageError(RuntimeError):
    """Base exception for temporary attachment storage."""


class InvalidAttachmentFilename(TemporaryFileStorageError):
    """The client supplied an unsafe or unsupported filename."""


class UnsupportedAttachmentType(TemporaryFileStorageError):
    """The upload is not recognizable as an allowed attachment type."""


class LegacyOfficeAttachment(UnsupportedAttachmentType):
    """The upload uses a legacy binary Office extension."""


class ArchiveAttachmentNotSupported(UnsupportedAttachmentType):
    """The upload is an archive rather than a supported attachment."""


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

    def store_attachment(
        self,
        file_stream: BinaryIO,
        original_filename: str,
        max_bytes: int,
        mime_type: str,
    ) -> StoredTemporaryFile:
        """Stream one validated upload to an atomic random path."""

        extension = self._validate_filename_and_media_type(
            original_filename,
            mime_type,
        )
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        allowed_bytes = min(max_bytes, max_bytes_for_extension(extension))
        storage_key = f"{uuid4().hex}{extension}"
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
                    if size_bytes > allowed_bytes:
                        raise AttachmentTooLarge(
                            f"The attachment exceeds the {allowed_bytes}-byte limit"
                        )

                    if len(leading_bytes) < 8:
                        needed = 8 - len(leading_bytes)
                        leading_bytes.extend(chunk[:needed])

                    output.write(chunk)
                    digest.update(chunk)

                output.flush()
                os.fsync(output.fileno())

            self._validate_content(
                extension,
                bytes(leading_bytes),
                part_path,
            )
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

    def store_pdf(
        self,
        file_stream: BinaryIO,
        original_filename: str,
        max_bytes: int,
        mime_type: str = PDF_MIME_TYPE,
    ) -> StoredTemporaryFile:
        """Store a PDF through the generic attachment validation path."""

        self._validate_original_filename(original_filename)
        if Path(original_filename.strip()).suffix.lower() != ".pdf":
            raise UnsupportedAttachmentType("Only .pdf attachments are supported")
        if mime_type.strip().lower() != PDF_MIME_TYPE:
            raise UnsupportedAttachmentType(
                "The upload is not a recognizable PDF upload"
            )
        return self.store_attachment(
            file_stream,
            original_filename,
            max_bytes,
            mime_type=mime_type,
        )

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

    @staticmethod
    def _validate_filename_and_media_type(
        original_filename: str,
        mime_type: str,
    ) -> str:
        try:
            return validate_filename_and_media_type(original_filename, mime_type)
        except InvalidAttachmentFilenameError as exc:
            raise InvalidAttachmentFilename(str(exc)) from exc
        except LegacyOfficeAttachmentError as exc:
            raise LegacyOfficeAttachment(str(exc)) from exc
        except ArchiveAttachmentNotSupportedError as exc:
            raise ArchiveAttachmentNotSupported(str(exc)) from exc
        except UnsupportedAttachmentTypeError as exc:
            raise UnsupportedAttachmentType(str(exc)) from exc

    @staticmethod
    def _validate_content(extension: str, leading: bytes, path: Path) -> None:
        if extension == ".pdf":
            if not leading.startswith(PDF_MAGIC_BYTES):
                raise UnsupportedAttachmentType(
                    "The upload is not a recognizable PDF upload"
                )
            return

        if extension in TEXT_LIKE_EXTENSIONS:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                raise UnsupportedAttachmentType(
                    "Text attachments must be UTF-8"
                ) from exc
            control_count = sum(
                1
                for character in text
                if ord(character) < 32 and character not in {"\t", "\n", "\r"}
            )
            if text and control_count / len(text) >= 0.01:
                raise UnsupportedAttachmentType(
                    "Text attachments contain binary control characters"
                )
            return

        expected_content_types = {
            ".docx": "wordprocessingml.document.main+xml",
            ".xlsx": "spreadsheetml.sheet.main+xml",
            ".pptx": "presentationml.presentation.main+xml",
        }
        expected_content_type = expected_content_types.get(extension)
        if expected_content_type is None:
            raise UnsupportedAttachmentType("Unsupported attachment type")
        if not leading.startswith(b"PK\x03\x04"):
            raise UnsupportedAttachmentType("Invalid Office document content")

        try:
            with ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 2_000:
                    raise UnsupportedAttachmentType("Office document has too many entries")
                total_uncompressed_bytes = 0
                for entry in entries:
                    total_uncompressed_bytes += entry.file_size
                    if total_uncompressed_bytes > 100 * 1024 * 1024:
                        raise UnsupportedAttachmentType(
                            "Office document is too large when decompressed"
                        )
                    if entry.file_size and entry.file_size / max(entry.compress_size, 1) > 100:
                        raise UnsupportedAttachmentType(
                            "Office document has an unsafe compression ratio"
                        )
                content_types = archive.read("[Content_Types].xml")
        except (BadZipFile, KeyError, OSError) as exc:
            raise UnsupportedAttachmentType("Invalid Office document content") from exc

        if expected_content_type.encode("ascii") not in content_types:
            raise UnsupportedAttachmentType("Office document type does not match filename")
