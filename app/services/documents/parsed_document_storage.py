"""Atomic JSON storage for structured PDF parsing results."""

from collections.abc import Mapping
import json
import os
from pathlib import Path
from uuid import uuid4

from app.services.documents.parsed_document import ParsedDocument
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    TemporaryFileStorage,
)


class ParsedDocumentStorageError(RuntimeError):
    """Structured parse output could not be safely stored or read."""


class ParsedDocumentStorage:
    """Store UTF-8 parsed JSON under the temporary document root."""

    def __init__(self, file_storage: TemporaryFileStorage) -> None:
        self.file_storage = file_storage

    def write_json(
        self,
        document_id: str,
        payload: ParsedDocument | Mapping[str, object],
    ) -> str:
        """Atomically write one parsed document and return its relative key."""

        storage_key = f"parsed/{document_id}.json"
        final_path = self._resolve(storage_key)
        part_path = final_path.with_name(
            f"{final_path.name}.{uuid4().hex}.part"
        )
        serializable = (
            payload.to_dict()
            if isinstance(payload, ParsedDocument)
            else payload
        )

        try:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(
                    serializable,
                    output,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(part_path, final_path)
            return storage_key
        except Exception as exc:
            try:
                part_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                raise ParsedDocumentStorageError(
                    "Parsed JSON temporary file could not be cleaned up"
                ) from cleanup_error
            if isinstance(exc, ParsedDocumentStorageError):
                raise
            raise ParsedDocumentStorageError(
                "Parsed document JSON could not be stored"
            ) from exc

    def read_json(self, storage_key: str) -> dict[str, object]:
        """Read one trusted relative JSON key after root-boundary validation."""

        path = self._resolve(storage_key)
        try:
            with path.open("r", encoding="utf-8") as source:
                payload = json.load(source)
        except Exception as exc:
            raise ParsedDocumentStorageError(
                "Parsed document JSON could not be read"
            ) from exc
        if not isinstance(payload, dict):
            raise ParsedDocumentStorageError(
                "Parsed document JSON must contain an object"
            )
        return payload

    def delete(self, storage_key: str) -> None:
        """Idempotently delete one parsed JSON file."""

        path = self._resolve(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise ParsedDocumentStorageError(
                "Parsed document JSON could not be deleted"
            ) from exc

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).is_file()

    def _resolve(self, storage_key: str) -> Path:
        try:
            return self.file_storage.resolve(storage_key)
        except AttachmentStorageError as exc:
            raise ParsedDocumentStorageError(
                "Invalid parsed document storage key"
            ) from exc
