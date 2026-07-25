"""Application service orchestrating temporary PDF attachment parsing."""

from collections.abc import Callable
from datetime import datetime, timezone

from app.db.models import (
    DocumentRecord,
    DocumentScope,
    DocumentStatus,
    InvalidDocumentStatusTransition,
)
import app.repositories.document_repository as document_repository
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.pdf_parser import PdfParser, PdfParsingError
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    TemporaryFileStorage,
)


class PdfParsingServiceError(RuntimeError):
    """Base application error for attachment parsing orchestration."""


class ParsingAttachmentNotFound(PdfParsingServiceError):
    """The internal document id does not identify a parseable attachment."""


class AttachmentParsingExpired(PdfParsingServiceError):
    """The attachment TTL expired before parsing began."""


class AlreadyParsingError(PdfParsingServiceError):
    """Another task already owns the current PARSING lifecycle state."""


class AttachmentParsingNotAllowed(PdfParsingServiceError):
    """The attachment lifecycle state does not permit parsing."""


class PdfParsingCompensationError(PdfParsingServiceError):
    """A parsing failure could not be fully compensated."""


class PdfParsingService:
    """Move ATTACHMENT records through PARSING into READY or FAILED."""

    def __init__(
        self,
        settings: TemporaryDocumentSettings,
        *,
        parser: PdfParser | None = None,
        file_storage: TemporaryFileStorage | None = None,
        parsed_storage: ParsedDocumentStorage | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.parser = parser or PdfParser()
        self.file_storage = file_storage or TemporaryFileStorage(
            settings.root_path,
            settings.write_chunk_bytes,
        )
        self.parsed_storage = parsed_storage or ParsedDocumentStorage(
            self.file_storage
        )
        self._now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def parse_attachment(self, document_id: str) -> DocumentRecord:
        """Parse one trusted attachment id without exposing a public API."""

        record = document_repository.get_document(document_id)
        if record is None or record.scope is not DocumentScope.ATTACHMENT:
            raise ParsingAttachmentNotFound("Attachment not found")
        if self._is_expired(record):
            raise AttachmentParsingExpired("Attachment has expired")
        if record.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
            return record
        if record.status is DocumentStatus.PARSING:
            raise AlreadyParsingError("Attachment is already being parsed")
        if record.status in {DocumentStatus.DELETING, DocumentStatus.DELETED}:
            raise AttachmentParsingNotAllowed(
                f"Cannot parse attachment in {record.status.value}"
            )
        if record.status not in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
            raise AttachmentParsingNotAllowed(
                f"Cannot parse attachment in {record.status.value}"
            )

        if record.status is DocumentStatus.FAILED and record.parsed_path:
            self.parsed_storage.delete(record.parsed_path)

        # A future multi-worker queue must replace this read/transition pair with
        # an atomic claim. The current stage intentionally has no distributed lock.
        try:
            parsing = document_repository.update_document_status(
                record.id,
                DocumentStatus.PARSING,
                parser_name=self.parser.name,
                parser_version=self.parser.version,
            )
        except (
            InvalidDocumentStatusTransition,
            document_repository.DocumentRepositoryError,
        ) as exc:
            current = document_repository.get_document(record.id)
            if current is None:
                raise ParsingAttachmentNotFound(
                    "Attachment disappeared"
                ) from exc
            if current.status is DocumentStatus.PARSING:
                raise AlreadyParsingError(
                    "Attachment is already being parsed"
                ) from exc
            if current.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
                return current
            raise AttachmentParsingNotAllowed(
                f"Cannot claim attachment in {current.status.value}"
            ) from exc
        if parsing is None:
            raise ParsingAttachmentNotFound("Attachment disappeared")

        try:
            source_path = self.file_storage.resolve(parsing.storage_path)
            parsed = self.parser.parse(
                source_path=source_path,
                document_id=parsing.id,
                original_filename=parsing.original_filename,
                max_pages=self.settings.max_pages,
                min_extracted_chars=self.settings.min_extracted_chars,
            )
        except PdfParsingError as exc:
            return self._mark_failed(parsing.id, exc.error_code, str(exc))
        except (AttachmentStorageError, ParsedDocumentStorageError) as exc:
            return self._mark_failed(
                parsing.id,
                "PDF_PARSE_FAILED",
                "PDF source or parse result storage failed",
                cause=exc,
            )
        except Exception as exc:
            return self._mark_failed(
                parsing.id,
                "PDF_PARSE_FAILED",
                "Unexpected PDF parsing failure",
                cause=exc,
            )

        try:
            parsed_path = self.parsed_storage.write_json(parsing.id, parsed)
        except Exception as exc:
            return self._mark_failed(
                parsing.id,
                "PDF_PARSE_FAILED",
                "Parsed document JSON could not be stored",
                cause=exc,
            )

        try:
            ready = document_repository.update_document_status(
                parsing.id,
                DocumentStatus.READY,
                parsed_path=parsed_path,
                parser_name=self.parser.name,
                parser_version=self.parser.version,
                page_count=parsed.page_count,
            )
            if ready is None:
                raise PdfParsingServiceError(
                    "Attachment disappeared before READY update"
                )
            return ready
        except Exception as exc:
            try:
                self.parsed_storage.delete(parsed_path)
            except Exception as cleanup_error:
                raise PdfParsingCompensationError(
                    "READY metadata failed and parsed JSON cleanup failed"
                ) from cleanup_error
            return self._mark_failed(
                parsing.id,
                "PDF_PARSE_FAILED",
                "READY metadata update failed",
                cause=exc,
            )

    def _mark_failed(
        self,
        document_id: str,
        error_code: str,
        error_message: str,
        *,
        cause: Exception | None = None,
    ) -> DocumentRecord:
        try:
            failed = document_repository.update_document_status(
                document_id,
                DocumentStatus.FAILED,
                parser_name=self.parser.name,
                parser_version=self.parser.version,
                error_code=error_code,
                error_message=error_message,
            )
        except Exception as exc:
            raise PdfParsingServiceError(
                "Attachment could not be marked FAILED"
            ) from exc
        if failed is None:
            raise PdfParsingServiceError(
                "Attachment disappeared before FAILED update"
            ) from cause
        return failed

    def _is_expired(self, record: DocumentRecord) -> bool:
        if record.expires_at is None:
            return True
        expires_at = datetime.fromisoformat(
            record.expires_at.replace("Z", "+00:00")
        )
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PdfParsingServiceError(
                "now_provider must return a timezone-aware datetime"
            )
        return expires_at <= now.astimezone(timezone.utc)
