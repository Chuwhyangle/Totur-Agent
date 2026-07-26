"""Claim temporary attachments for explicit user-requested retries."""

from collections.abc import Callable
from datetime import datetime, timezone
import logging

from app.db.models import (
    DocumentRecord,
    DocumentStatus,
    InvalidDocumentStatusTransition,
)
import app.repositories.document_repository as document_repository
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.settings import (
    TemporaryDocumentSettings,
    load_temporary_document_settings,
)
from app.services.documents.temporary_file_storage import TemporaryFileStorage


logger = logging.getLogger(__name__)


class AttachmentRetryServiceError(RuntimeError):
    """Base error for attachment retry claims."""


class AttachmentRetryNotFound(AttachmentRetryServiceError):
    """The caller cannot access a retryable attachment."""


class AttachmentAlreadyProcessing(AttachmentRetryServiceError):
    """A processing task already owns this attachment."""


class AttachmentRetryNotAllowed(AttachmentRetryServiceError):
    """The attachment is complete or otherwise cannot be retried."""


class AttachmentRetryPreparationError(AttachmentRetryServiceError):
    """Stale parsed output could not be removed before a full retry."""


class AttachmentRetryService:
    """Validate ownership/TTL/state and CAS an attachment into PARSING."""

    def __init__(
        self,
        settings: TemporaryDocumentSettings,
        *,
        parsed_storage: ParsedDocumentStorage | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        if parsed_storage is None:
            file_storage = TemporaryFileStorage(
                settings.root_path,
                settings.write_chunk_bytes,
            )
            parsed_storage = ParsedDocumentStorage(file_storage)
        self.parsed_storage = parsed_storage
        self._now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def claim_retry(
        self,
        document_id: str,
        user_id: str,
        session_id: int,
    ) -> DocumentRecord:
        """Claim one unexpired FAILED/UPLOADED attachment via SQLite CAS."""

        record = document_repository.get_accessible_attachment(
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            now=self._utc_now(),
        )
        if record is None:
            raise AttachmentRetryNotFound("Session or attachment not found")
        self._validate_retry_state(record)

        # Claim first so concurrent retries cannot delete each other's parsed
        # output. Only the SQLite CAS winner performs preparation and schedules
        # the background pipeline.
        try:
            claimed = document_repository.update_document_status(
                record.id,
                DocumentStatus.PARSING,
                expected_status=record.status,
            )
        except (
            InvalidDocumentStatusTransition,
            document_repository.DocumentRepositoryError,
        ) as exc:
            self._raise_current_state(record.id, user_id, session_id, exc)
        if claimed is None:
            raise AttachmentRetryNotFound("Session or attachment not found")

        if record.parsed_path:
            try:
                self.parsed_storage.delete(record.parsed_path)
            except ParsedDocumentStorageError as exc:
                try:
                    document_repository.update_document_status(
                        record.id,
                        DocumentStatus.FAILED,
                        error_code="ATTACHMENT_RETRY_PREPARATION_FAILED",
                        error_message="Attachment retry preparation failed",
                    )
                except Exception as state_error:
                    current = document_repository.get_document(record.id)
                    logger.error(
                        "attachment_retry_failure_state_update_failed "
                        "document_id=%s error_type=%s status=%s",
                        record.id,
                        type(state_error).__name__,
                        current.status.value if current is not None else "MISSING",
                    )
                raise AttachmentRetryPreparationError(
                    "Parsed attachment cleanup failed"
                ) from exc
        return claimed

    @staticmethod
    def _validate_retry_state(record: DocumentRecord) -> None:
        if record.status in {DocumentStatus.PARSING, DocumentStatus.INDEXING}:
            raise AttachmentAlreadyProcessing(
                "Attachment processing is already in progress"
            )
        if record.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
            # Missing-index detection first downgrades these records to FAILED.
            raise AttachmentRetryNotAllowed(
                "A complete attachment cannot be retried"
            )
        if record.status not in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
            raise AttachmentRetryNotFound("Session or attachment not found")

    def _raise_current_state(
        self,
        document_id: str,
        user_id: str,
        session_id: int,
        cause: Exception,
    ) -> None:
        current = document_repository.get_accessible_attachment(
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            now=self._utc_now(),
        )
        if current is None:
            raise AttachmentRetryNotFound(
                "Session or attachment not found"
            ) from cause
        if current.status in {DocumentStatus.PARSING, DocumentStatus.INDEXING}:
            raise AttachmentAlreadyProcessing(
                "Attachment processing is already in progress"
            ) from cause
        if current.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
            raise AttachmentRetryNotAllowed(
                "A complete attachment cannot be retried"
            ) from cause
        raise AttachmentRetryNotAllowed(
            f"Attachment cannot be retried from {current.status.value}"
        ) from cause

    def _utc_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise AttachmentRetryServiceError(
                "now_provider must return a timezone-aware datetime"
            )
        return now.astimezone(timezone.utc)


def get_attachment_retry_service() -> AttachmentRetryService:
    """Build a retry claim service without embedding or Chroma clients."""

    return AttachmentRetryService(load_temporary_document_settings())
