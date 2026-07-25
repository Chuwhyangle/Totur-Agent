"""Local MVP pipeline for parsing and indexing uploaded attachments."""

import logging
import time

from app.clients.embedding_client import EmbeddingClient
from app.db.models import DocumentRecord, DocumentScope, DocumentStatus
import app.repositories.document_repository as document_repository
from app.repositories.attachment_vector_repository import AttachmentVectorRepository
from app.services.documents.attachment_chunker import AttachmentChunker
from app.services.documents.attachment_indexing_service import (
    AttachmentIndexingService,
)
from app.services.documents.parsed_document_storage import ParsedDocumentStorage
from app.services.documents.pdf_parser import PdfParser
from app.services.documents.pdf_parsing_service import PdfParsingService
from app.services.documents.settings import load_temporary_document_settings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


logger = logging.getLogger(__name__)


class AttachmentProcessingServiceError(RuntimeError):
    """Base error for the parse-and-index pipeline."""


class ProcessingAttachmentNotFound(AttachmentProcessingServiceError):
    """The trusted document id is absent or not an attachment."""


class AttachmentAlreadyProcessing(AttachmentProcessingServiceError):
    """A PARSING or INDEXING task already owns this attachment."""


class AttachmentProcessingNotAllowed(AttachmentProcessingServiceError):
    """The lifecycle state cannot enter processing."""


class AttachmentProcessingService:
    """Drive UPLOADED/FAILED attachments through parse and index stages."""

    def __init__(
        self,
        parsing_service: PdfParsingService,
        indexing_service: AttachmentIndexingService,
    ) -> None:
        self.parsing_service = parsing_service
        self.indexing_service = indexing_service

    def process_attachment(self, document_id: str) -> DocumentRecord:
        started = time.monotonic()
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

        try:
            parsed_record = self.parsing_service.parse_attachment(document_id)
            if parsed_record.status is DocumentStatus.FAILED:
                return parsed_record
            if parsed_record.status in {
                DocumentStatus.READY,
                DocumentStatus.PARTIAL,
            }:
                return parsed_record
            return self.indexing_service.index_attachment(document_id)
        finally:
            current = document_repository.get_document(document_id)
            logger.info(
                "attachment_processing document_id=%s status=%s elapsed_ms=%d",
                document_id,
                current.status.value if current is not None else "MISSING",
                int((time.monotonic() - started) * 1000),
            )


def get_attachment_processing_service() -> AttachmentProcessingService:
    """Build the local BackgroundTasks pipeline from runtime settings."""

    settings = load_temporary_document_settings()
    file_storage = TemporaryFileStorage(
        settings.root_path,
        settings.write_chunk_bytes,
    )
    parsed_storage = ParsedDocumentStorage(file_storage)
    vector_repository = AttachmentVectorRepository()
    parsing_service = PdfParsingService(
        settings,
        parser=PdfParser(),
        file_storage=file_storage,
        parsed_storage=parsed_storage,
    )
    indexing_service = AttachmentIndexingService(
        settings,
        parsed_storage,
        vector_repository,
        chunker=AttachmentChunker(
            settings.chunk_chars,
            settings.chunk_overlap_chars,
        ),
        embedding_client=EmbeddingClient(),
    )
    return AttachmentProcessingService(parsing_service, indexing_service)


def process_attachment_background(
    document_id: str,
    service: AttachmentProcessingService,
) -> None:
    """Run after the HTTP response; BackgroundTasks has no durable recovery."""

    try:
        service.process_attachment(document_id)
    except Exception as exc:
        # Keep the exception out of the already-sent upload response. Recovery of
        # stale PARSING/INDEXING rows requires a future durable worker queue.
        logger.error(
            "attachment_background_processing_failed document_id=%s error_type=%s",
            document_id,
            type(exc).__name__,
        )
