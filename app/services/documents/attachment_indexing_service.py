"""Index parsed temporary attachments into their isolated Chroma collection."""

from collections.abc import Callable
from datetime import datetime, timezone

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.models import DocumentRecord, DocumentScope, DocumentStatus
import app.repositories.document_repository as document_repository
from app.repositories.attachment_vector_repository import (
    AttachmentVectorRepository,
)
from app.services.documents.attachment_chunker import (
    AttachmentChunker,
    AttachmentChunkingError,
)
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedDocumentValidationError,
)
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.rag_settings import EMBEDDING_BATCH_SIZE


class AttachmentIndexingServiceError(RuntimeError):
    """Base error for attachment indexing orchestration."""


class IndexingAttachmentNotFound(AttachmentIndexingServiceError):
    """The trusted document id is absent or not an attachment."""


class AttachmentIndexingNotAllowed(AttachmentIndexingServiceError):
    """The document is not in INDEXING state."""


class AttachmentIndexingCompensationError(AttachmentIndexingServiceError):
    """A partial vector write could not be safely removed."""


class AttachmentIndexingService:
    """Validate parsed JSON, chunk, embed, index, then publish READY."""

    def __init__(
        self,
        settings: TemporaryDocumentSettings,
        parsed_storage: ParsedDocumentStorage,
        vector_repository: AttachmentVectorRepository,
        *,
        chunker: AttachmentChunker | None = None,
        embedding_client: EmbeddingClient | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.parsed_storage = parsed_storage
        self.vector_repository = vector_repository
        self.chunker = chunker or AttachmentChunker(
            settings.chunk_chars,
            settings.chunk_overlap_chars,
        )
        self.embedding_client = embedding_client or EmbeddingClient()
        self._now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def index_attachment(self, document_id: str) -> DocumentRecord:
        record = document_repository.get_document(document_id)
        if record is None or record.scope is not DocumentScope.ATTACHMENT:
            raise IndexingAttachmentNotFound("Attachment not found")
        if record.status in {DocumentStatus.READY, DocumentStatus.PARTIAL}:
            return record
        if record.status is not DocumentStatus.INDEXING:
            raise AttachmentIndexingNotAllowed(
                f"Cannot index attachment in {record.status.value}"
            )
        if self._is_expired(record):
            return self._mark_failed(
                record.id,
                "ATTACHMENT_EXPIRED_DURING_PROCESSING",
                "Attachment expired before indexing",
            )

        try:
            payload = self.parsed_storage.read_json(record.parsed_path or "")
            parsed = ParsedDocument.from_dict(payload)
            parsed.validate_identity(
                document_id=record.id,
                original_filename=record.original_filename,
                page_count=record.page_count,
            )
        except (ParsedDocumentStorageError, ParsedDocumentValidationError) as exc:
            return self._mark_failed(
                record.id,
                "PARSED_DOCUMENT_INVALID",
                "Parsed document JSON is invalid",
                cause=exc,
            )

        try:
            chunks = self.chunker.chunk(parsed)
            if not chunks:
                raise AttachmentChunkingError(
                    "Parsed document produced no retrieval chunks"
                )
        except Exception as exc:
            return self._mark_failed(
                record.id,
                "DOCUMENT_CHUNKING_FAILED",
                "Attachment text could not be chunked",
                cause=exc,
            )

        try:
            embeddings: list[list[float]] = []
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                batch_embeddings = self.embedding_client.embed_texts(
                    [chunk.text for chunk in batch]
                )
                if len(batch_embeddings) != len(batch):
                    raise EmbeddingError(
                        "Embedding response count does not match chunk count"
                    )
                embeddings.extend(batch_embeddings)
            if len(embeddings) != len(chunks):
                raise EmbeddingError(
                    "Embedding response count does not match chunk count"
                )
        except Exception as exc:
            return self._mark_failed(
                record.id,
                "EMBEDDING_FAILED",
                "Attachment embeddings could not be generated",
                cause=exc,
            )

        if self._is_expired(record):
            return self._mark_failed(
                record.id,
                "ATTACHMENT_EXPIRED_DURING_PROCESSING",
                "Attachment expired before vector indexing",
            )

        try:
            self.vector_repository.upsert_document_chunks(
                chunks=chunks,
                embeddings=embeddings,
                user_id=record.user_id or "",
                session_id=record.session_id if record.session_id is not None else -1,
                expires_at=record.expires_at or "",
            )
        except Exception as exc:
            self._compensate_vectors(record.id, exc)
            return self._mark_failed(
                record.id,
                "VECTOR_INDEX_FAILED",
                "Attachment vectors could not be indexed",
                cause=exc,
            )

        if self._is_expired(record):
            self._compensate_vectors(
                record.id,
                AttachmentIndexingServiceError(
                    "Attachment expired after vector indexing"
                ),
            )
            return self._mark_failed(
                record.id,
                "ATTACHMENT_EXPIRED_DURING_PROCESSING",
                "Attachment expired during vector indexing",
            )

        try:
            ready = document_repository.update_document_status(
                record.id,
                DocumentStatus.READY,
            )
            if ready is None:
                raise AttachmentIndexingServiceError(
                    "Attachment disappeared before READY update"
                )
            return ready
        except Exception as exc:
            self._compensate_vectors(record.id, exc)
            return self._mark_failed(
                record.id,
                "VECTOR_INDEX_FAILED",
                "READY metadata update failed after indexing",
                cause=exc,
            )

    def _compensate_vectors(self, document_id: str, cause: Exception) -> None:
        try:
            self.vector_repository.delete_document(document_id)
        except Exception as cleanup_error:
            raise AttachmentIndexingCompensationError(
                "Partial attachment vectors could not be removed"
            ) from cleanup_error

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
                error_code=error_code,
                error_message=error_message,
            )
        except Exception as exc:
            raise AttachmentIndexingServiceError(
                "Attachment could not be marked FAILED"
            ) from exc
        if failed is None:
            raise AttachmentIndexingServiceError(
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
            raise AttachmentIndexingServiceError(
                "now_provider must return a timezone-aware datetime"
            )
        return expires_at <= now.astimezone(timezone.utc)
