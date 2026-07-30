"""Application service for temporary conversation PDF attachments."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.db.models import DocumentRecord, DocumentScope, DocumentStatus
from app.repositories.attachment_vector_repository import AttachmentVectorRepository
from app.repositories.document_repository import (
    DocumentRepositoryError,
    count_accessible_session_attachments,
    create_attachment_document,
    delete_document_record,
    get_accessible_attachment,
    get_attachment_for_cleanup,
    list_accessible_session_attachments,
    update_document_status,
)
from app.repositories.session_repository import get_session
from app.services.documents.settings import (
    TemporaryDocumentSettings,
    load_temporary_document_settings,
)
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    TemporaryFileStorage,
)


class TemporaryDocumentServiceError(RuntimeError):
    """Base exception for temporary document orchestration."""


class AttachmentNotFoundError(TemporaryDocumentServiceError):
    """The session or attachment is absent or not owned by the caller."""


class AttachmentLimitExceeded(TemporaryDocumentServiceError):
    """The session already has the maximum number of active attachments."""


class AttachmentCreationError(TemporaryDocumentServiceError):
    """The file was stored but its metadata could not be created."""


class AttachmentCompensationError(AttachmentCreationError):
    """Metadata creation and its compensating file deletion both failed."""


class AttachmentCleanupError(TemporaryDocumentServiceError):
    """Attachment cleanup stopped before the DELETED state."""


class TemporaryDocumentService:
    """Coordinate ownership, TTL, storage, metadata, and deletion state."""

    def __init__(
        self,
        settings: TemporaryDocumentSettings,
        storage: TemporaryFileStorage | None = None,
        vector_repository: AttachmentVectorRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or TemporaryFileStorage(
            settings.root_path,
            settings.write_chunk_bytes,
        )
        self.vector_repository = vector_repository
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def create_attachment(
        self,
        user_id: str,
        session_id: int,
        upload_file,
    ) -> DocumentRecord:
        """Validate and store one attachment, compensating on DB failure."""

        self._require_owned_session(user_id, session_id)
        now = self._utc_now()

        # This count-then-create check is sufficient for the local SQLite MVP.
        # Multi-instance deployments need a transaction, lock, or DB constraint.
        active_count = count_accessible_session_attachments(
            user_id=user_id,
            session_id=session_id,
            now=now,
        )
        if active_count >= self.settings.max_files_per_session:
            raise AttachmentLimitExceeded(
                "The session attachment limit has been reached"
            )

        stored = self.storage.store_pdf(
            upload_file.file,
            upload_file.filename or "",
            self.settings.max_bytes,
            mime_type=upload_file.content_type or "",
        )
        expires_at = now + timedelta(hours=self.settings.ttl_hours)

        # Filesystem and SQLite cannot commit atomically. A DB failure triggers
        # best-effort compensation; a process crash in this gap can leave an
        # orphan file for a future cleanup service to scan.
        try:
            return create_attachment_document(
                user_id=user_id,
                session_id=session_id,
                original_filename=upload_file.filename or "",
                mime_type=upload_file.content_type or "",
                size_bytes=stored.size_bytes,
                storage_path=stored.storage_key,
                content_hash=f"sha256:{stored.sha256}",
                expires_at=expires_at,
            )
        except Exception as create_error:
            try:
                self.storage.delete(stored.storage_key)
            except AttachmentStorageError as cleanup_error:
                raise AttachmentCompensationError(
                    "Attachment metadata creation and file compensation failed"
                ) from cleanup_error
            raise AttachmentCreationError(
                "Attachment metadata could not be created"
            ) from create_error

    def get_attachment(
        self,
        document_id: str,
        user_id: str,
        session_id: int,
    ) -> DocumentRecord:
        """Return one unexpired attachment after centralized ownership checks."""

        self._require_owned_session(user_id, session_id)
        record = get_accessible_attachment(
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            now=self._utc_now(),
        )
        if record is None:
            raise AttachmentNotFoundError("Session or attachment not found")
        return record

    def list_attachments(
        self,
        user_id: str,
        session_id: int,
    ) -> list[DocumentRecord]:
        """List unexpired attachments for one owned session."""

        self._require_owned_session(user_id, session_id)
        return list_accessible_session_attachments(
            user_id=user_id,
            session_id=session_id,
            now=self._utc_now(),
        )

    def delete_attachment(
        self,
        document_id: str,
        user_id: str,
        session_id: int,
    ) -> None:
        """Delete files, finish lifecycle state, then purge metadata."""

        self._require_owned_session(user_id, session_id)
        record = get_accessible_attachment(
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
            now=self._utc_now(),
        )
        if record is not None:
            deleting = update_document_status(
                document_id,
                DocumentStatus.DELETING,
            )
            if deleting is None:
                raise AttachmentNotFoundError(
                    "Session or attachment not found"
                )
            self._cleanup_attachment_record(deleting)
            return

        cleanup_record = get_attachment_for_cleanup(document_id)
        if not self._is_owned_attachment(
            cleanup_record,
            user_id,
            session_id,
        ):
            raise AttachmentNotFoundError(
                "Session or attachment not found"
            )
        self._cleanup_attachment_record(cleanup_record)

    def retry_attachment_cleanup(self, document_id: str) -> bool:
        """Retry trusted internal cleanup for DELETING/DELETED metadata."""

        record = get_attachment_for_cleanup(document_id)
        if record is None:
            return False
        self._cleanup_attachment_record(record)
        return True

    def reclaim_expired_attachment(self, record: DocumentRecord) -> bool:
        """Claim one expired attachment into DELETING, then run full cleanup.

        TTL expiry only hides a record from the accessible-attachment queries,
        so its file, parsed JSON, vectors, and metadata still need reclaiming.
        """

        if record.scope is not DocumentScope.ATTACHMENT:
            return False
        # DELETING/DELETED records already belong to the stale cleanup path.
        if record.status in {DocumentStatus.DELETING, DocumentStatus.DELETED}:
            return False

        # Compare-and-swap so a concurrent retry, delete, or processing
        # transition wins instead of having its files removed underneath it.
        try:
            claimed = update_document_status(
                record.id,
                DocumentStatus.DELETING,
                expected_status=record.status,
            )
        except DocumentRepositoryError:
            return False
        if claimed is None:
            return False

        self._cleanup_attachment_record(claimed)
        return True

    def _cleanup_attachment_record(self, record: DocumentRecord) -> None:
        if record.status is DocumentStatus.DELETING:
            storage_keys = [record.storage_path]
            # parsed_path is a relative key under this same storage root.
            if record.parsed_path and record.parsed_path not in storage_keys:
                storage_keys.append(record.parsed_path)

            try:
                for storage_key in storage_keys:
                    self.storage.delete(storage_key)
            except AttachmentStorageError as exc:
                # Keep DELETING so this idempotent operation can be retried.
                raise AttachmentCleanupError(
                    "Attachment file cleanup failed"
                ) from exc

            try:
                vector_repository = (
                    self.vector_repository or AttachmentVectorRepository()
                )
                vector_repository.delete_document(record.id)
            except Exception as exc:
                # File deletion is idempotent, so a retry can continue here.
                raise AttachmentCleanupError(
                    "Attachment vector cleanup failed"
                ) from exc

            try:
                deleted = update_document_status(
                    record.id,
                    DocumentStatus.DELETED,
                )
                if deleted is None:
                    raise AttachmentCleanupError(
                        "Attachment metadata disappeared during cleanup"
                    )
            except AttachmentCleanupError:
                raise
            except Exception as exc:
                raise AttachmentCleanupError(
                    "Attachment metadata cleanup failed"
                ) from exc

        try:
            delete_document_record(record.id)
        except Exception as exc:
            raise AttachmentCleanupError(
                "Attachment metadata cleanup failed"
            ) from exc

    @staticmethod
    def _is_owned_attachment(
        record: DocumentRecord | None,
        user_id: str,
        session_id: int,
    ) -> bool:
        return (
            record is not None
            and record.scope is DocumentScope.ATTACHMENT
            and record.user_id == user_id
            and record.session_id == session_id
        )

    def _require_owned_session(self, user_id: str, session_id: int) -> None:
        # user_id is a temporary identity mechanism until authentication exists.
        session = get_session(session_id)
        if session is None or session.user_id != user_id:
            raise AttachmentNotFoundError("Session or attachment not found")

    def _utc_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise TemporaryDocumentServiceError(
                "now_provider must return a timezone-aware datetime"
            )
        return now.astimezone(timezone.utc)


def get_temporary_document_service() -> TemporaryDocumentService:
    """Build a service from validated environment settings for one request."""

    # Vector storage is initialized lazily by cleanup so upload/list/get do not
    # fail before metadata is durable when Chroma is temporarily unavailable.
    return TemporaryDocumentService(load_temporary_document_settings())
