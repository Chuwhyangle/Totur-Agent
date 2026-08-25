"""Safe storage for durable user knowledge documents."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO
from uuid import uuid4

from app.config import StorageConfig


MAX_KNOWLEDGE_DOCUMENT_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}


class KnowledgeDocumentStorageError(RuntimeError):
    """Base storage error for knowledge documents."""


class InvalidKnowledgeDocumentFilename(KnowledgeDocumentStorageError):
    """The supplied filename is not a safe single filename."""


class UnsupportedKnowledgeDocumentType(KnowledgeDocumentStorageError):
    """The filename or media type is not supported."""


class KnowledgeDocumentTooLarge(KnowledgeDocumentStorageError):
    """The upload exceeded the 50 MiB limit."""


class KnowledgeDocumentStorage:
    """Store uploads below DATA_DIR/knowledge_docs using random keys."""

    def __init__(
        self,
        root_path: Path | str | None = None,
        *,
        max_bytes: int = MAX_KNOWLEDGE_DOCUMENT_BYTES,
        write_chunk_bytes: int = 64 * 1024,
    ) -> None:
        self.root_path = Path(
            root_path if root_path is not None else StorageConfig.from_env().DATA_DIR
        ).expanduser().resolve(strict=False) / "knowledge_docs"
        self.max_bytes = max_bytes
        self.write_chunk_bytes = write_chunk_bytes

    def stage_upload(
        self,
        file_stream: BinaryIO,
        original_filename: str,
        media_type: str = "",
    ) -> tuple[str, int, str]:
        extension = self._validate_filename(original_filename, media_type)
        storage_key = f"knowledge_docs/{uuid4().hex}{extension}"
        final_path = self.resolve(storage_key)
        part_path = final_path.with_name(f"{final_path.name}.part")
        size = 0
        digest = hashlib.sha256()
        completed = False
        try:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("xb") as output:
                while True:
                    chunk = file_stream.read(self.write_chunk_bytes)
                    if chunk is None or not isinstance(chunk, (bytes, bytearray)):
                        raise KnowledgeDocumentStorageError(
                            "Upload stream did not return bytes"
                        )
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise KnowledgeDocumentTooLarge(
                            "Knowledge document exceeds the 50 MiB limit"
                        )
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(part_path, final_path)
            completed = True
            return storage_key, size, digest.hexdigest()
        finally:
            if not completed and part_path.exists():
                part_path.unlink(missing_ok=True)

    def delete(self, storage_key: str | None) -> None:
        if not storage_key:
            return
        self.resolve(storage_key).unlink(missing_ok=True)

    def resolve(self, storage_key: str) -> Path:
        if not storage_key or not storage_key.strip() or "\x00" in storage_key:
            raise KnowledgeDocumentStorageError("Invalid storage key")
        posix = PurePosixPath(storage_key)
        windows = PureWindowsPath(storage_key)
        if (
            "\\" in storage_key
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or any(part in {"", ".", ".."} for part in posix.parts)
        ):
            raise KnowledgeDocumentStorageError("Invalid storage key")
        candidate = (self.root_path.parent / Path(*posix.parts)).resolve(strict=False)
        try:
            candidate.relative_to(self.root_path.parent)
        except ValueError as exc:
            raise KnowledgeDocumentStorageError("Storage key escapes root") from exc
        return candidate

    @staticmethod
    def _validate_filename(filename: str, media_type: str) -> str:
        if not filename or not filename.strip() or "\x00" in filename:
            raise InvalidKnowledgeDocumentFilename("Knowledge filename is invalid")
        name = filename.strip()
        windows = PureWindowsPath(name)
        if (
            "/" in name
            or "\\" in name
            or name in {".", ".."}
            or windows.is_absolute()
            or windows.drive
            or any(ord(char) < 32 for char in name)
        ):
            raise InvalidKnowledgeDocumentFilename("Knowledge filename is invalid")
        extension = Path(name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedKnowledgeDocumentType(
                "Only PDF and Markdown documents are supported"
            )
        expected = "application/pdf" if extension == ".pdf" else "text/markdown"
        if media_type and media_type.strip().lower() not in {expected, ""}:
            raise UnsupportedKnowledgeDocumentType("Filename and MIME type do not match")
        return extension
