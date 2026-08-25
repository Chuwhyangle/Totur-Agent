"""Local MVP pipeline for parsing and indexing uploaded attachments."""

import logging
import time

from app.db.models import DocumentRecord, DocumentScope, DocumentStatus
import app.repositories.document_repository as document_repository
from app.services.documents.attachment_parsers import AttachmentParserDispatch
from app.services.documents.parsed_document_storage import ParsedDocumentStorage
from app.services.documents.attachment_parsing_service import AttachmentParsingService
from app.services.documents.settings import load_temporary_document_settings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


logger = logging.getLogger(__name__)

PROCESSING_SERVICE_UNAVAILABLE = "PROCESSING_SERVICE_UNAVAILABLE"
ATTACHMENT_PROCESSING_FAILED = "ATTACHMENT_PROCESSING_FAILED"


class AttachmentProcessingServiceError(RuntimeError):
    """Base error for the parse-and-index pipeline."""


class ProcessingAttachmentNotFound(AttachmentProcessingServiceError):
    """The trusted document id is absent or not an attachment."""


class AttachmentAlreadyProcessing(AttachmentProcessingServiceError):
    """A PARSING or INDEXING task already owns this attachment."""


class AttachmentProcessingNotAllowed(AttachmentProcessingServiceError):
    """The lifecycle state cannot enter processing."""


class AttachmentProcessingService:
    """Drive temporary attachments through parse and index stages."""

    def __init__(
        self,
        parsing_service: AttachmentParsingService,
        indexing_service: object | None = None,
    ) -> None:
        self.parsing_service = parsing_service
        self.indexing_service = indexing_service

    def process_attachment(self, document_id: str) -> DocumentRecord:
        """Claim an UPLOADED/FAILED record, then parse and index it."""

        record = document_repository.get_document(document_id)
        if record is None or record.scope is not DocumentScope.ATTACHMENT:
            raise ProcessingAttachmentNotFound("Attachment not found")
        if record.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
            return record
        if record.status in {DocumentStatus.PARSING, DocumentStatus.INDEXING}:
            raise AttachmentAlreadyProcessing(
                f"Attachment is already {record.status.value.lower()}"
            )
        if record.status in {DocumentStatus.DELETING, DocumentStatus.DELETED}:
            raise AttachmentProcessingNotAllowed(
                f"Cannot process attachment in {record.status.value}"
            )
        if record.status not in {DocumentStatus.UPLOADED, DocumentStatus.FAILED}:
            raise AttachmentProcessingNotAllowed(
                f"Cannot process attachment in {record.status.value}"
            )
        return self._run_pipeline(document_id, claimed=False)

    def process_claimed_attachment(self, document_id: str) -> DocumentRecord:
        """Resume the PARSING claim acquired synchronously by retry."""

        record = document_repository.get_document(document_id)
        if record is None or record.scope is not DocumentScope.ATTACHMENT:
            raise ProcessingAttachmentNotFound("Attachment not found")
        if record.status in {
            DocumentStatus.INDEXING,
            DocumentStatus.READY,
            DocumentStatus.PARTIAL,
        }:
            return record
        if record.status is not DocumentStatus.PARSING:
            raise AttachmentProcessingNotAllowed(
                f"Cannot resume attachment in {record.status.value}"
            )
        return self._run_pipeline(document_id, claimed=True)

    def _run_pipeline(
        self,
        document_id: str,
        *,
        claimed: bool,
    ) -> DocumentRecord:
        started = time.monotonic()
        try:
            if claimed:
                parsed_record = self.parsing_service.parse_claimed_attachment(
                    document_id
                )
            else:
                parsed_record = self.parsing_service.parse_attachment(document_id)
            if parsed_record.status is DocumentStatus.FAILED:
                return parsed_record
            if parsed_record.status in {
                DocumentStatus.READY,
                DocumentStatus.PARTIAL,
            }:
                return parsed_record
            # Parsed JSON is the source used by chat now.  Keep the optional
            # indexer only for compatibility with older callers and recovery
            # data; production assembly does not create embedding/Chroma deps.
            if self.indexing_service is not None:
                index_attachment = getattr(self.indexing_service, "index_attachment")
                return index_attachment(document_id)
            ready = document_repository.update_document_status(
                document_id,
                DocumentStatus.READY,
                expected_status=DocumentStatus.INDEXING,
            )
            if ready is None:
                raise AttachmentProcessingServiceError(
                    "Attachment disappeared before READY update"
                )
            return ready
        finally:
            current = document_repository.get_document(document_id)
            logger.info(
                "attachment_processing document_id=%s status=%s elapsed_ms=%d",
                document_id,
                current.status.value if current is not None else "MISSING",
                int((time.monotonic() - started) * 1000),
            )


def get_attachment_processing_service() -> AttachmentProcessingService:
    """Build the local pipeline only after an HTTP response is committed."""

    settings = load_temporary_document_settings()
    file_storage = TemporaryFileStorage(
        settings.root_path,
        settings.write_chunk_bytes,
    )
    parsed_storage = ParsedDocumentStorage(file_storage)
    parsing_service = AttachmentParsingService(
        settings,
        parser=AttachmentParserDispatch(),
        file_storage=file_storage,
        parsed_storage=parsed_storage,
    )
    return AttachmentProcessingService(parsing_service)


def process_attachment_background(
    document_id: str,
    service: AttachmentProcessingService | None = None,
) -> None:
    """Lazily build and run the normal pipeline after the HTTP response."""

    _run_attachment_background(document_id, claimed=False, service=service)


def process_claimed_attachment_background(document_id: str) -> None:
    """Lazily build and resume a retry claim after returning HTTP 202."""

    _run_attachment_background(document_id, claimed=True)


def _resolve_attachment_processing_service() -> AttachmentProcessingService:
    """Honor FastAPI test overrides without restoring an eager route dependency."""

    try:
        from app.main import app

        override = app.dependency_overrides.get(
            get_attachment_processing_service
        )
    except (ImportError, AttributeError):
        override = None
    return override() if override is not None else get_attachment_processing_service()


def _run_attachment_background(
    document_id: str,
    *,
    claimed: bool,
    service: AttachmentProcessingService | None = None,
) -> None:
    try:
        resolved_service = service or _resolve_attachment_processing_service()
    except Exception as exc:
        current_status = _mark_background_failure(
            document_id,
            error_code=PROCESSING_SERVICE_UNAVAILABLE,
            error_message="Attachment processing service is unavailable",
        )
        _log_background_failure(document_id, exc, current_status)
        return

    try:
        if claimed:
            resolved_service.process_claimed_attachment(document_id)
        else:
            resolved_service.process_attachment(document_id)
    except AttachmentAlreadyProcessing:
        current = document_repository.get_document(document_id)
        logger.info(
            "attachment_background_processing_skipped document_id=%s "
            "status=%s reason=already_processing",
            document_id,
            current.status.value if current is not None else "MISSING",
        )
    except Exception as exc:
        current_status = _mark_background_failure(
            document_id,
            error_code=ATTACHMENT_PROCESSING_FAILED,
            error_message="Attachment processing failed unexpectedly",
        )
        _log_background_failure(document_id, exc, current_status)


def _mark_background_failure(
    document_id: str,
    *,
    error_code: str,
    error_message: str,
) -> str:
    current = document_repository.get_document(document_id)
    if current is None:
        return "MISSING"
    if current.status not in {
        DocumentStatus.UPLOADED,
        DocumentStatus.PARSING,
        DocumentStatus.INDEXING,
    }:
        return current.status.value

    try:
        failed = document_repository.update_document_status(
            document_id,
            DocumentStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )
    except Exception as exc:
        latest = document_repository.get_document(document_id)
        logger.error(
            "attachment_background_failure_state_update_failed "
            "document_id=%s error_type=%s status=%s",
            document_id,
            type(exc).__name__,
            latest.status.value if latest is not None else "MISSING",
        )
        return latest.status.value if latest is not None else "MISSING"
    return failed.status.value if failed is not None else "MISSING"


def _log_background_failure(
    document_id: str,
    error: Exception,
    current_status: str,
) -> None:
    # Deliberately omit exception text/configuration/path/PDF content.
    logger.error(
        "attachment_background_processing_failed document_id=%s "
        "error_type=%s status=%s",
        document_id,
        type(error).__name__,
        current_status,
    )
