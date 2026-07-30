"""Bounded startup recovery for local single-instance attachment tasks."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from app.db.models import DocumentRecord, DocumentStatus
import app.repositories.document_repository as document_repository
from app.services.documents.attachment_processing_service import (
    process_attachment_background,
)
from app.services.documents.settings import (
    TemporaryDocumentSettings,
    load_temporary_document_settings,
)
from app.services.documents.temporary_document_service import (
    TemporaryDocumentService,
    get_temporary_document_service,
)


logger = logging.getLogger(__name__)

PROCESS_INTERRUPTED = "PROCESS_INTERRUPTED"


@dataclass(frozen=True)
class AttachmentRecoveryResult:
    scanned: int
    processing_recovered: int
    cleanup_recovered: int
    failures: int
    expired_reclaimed: int = 0


class AttachmentRecoveryService:
    """Run one bounded recovery pass; this is not a production task queue."""

    def __init__(
        self,
        settings: TemporaryDocumentSettings,
        *,
        now_provider: Callable[[], datetime] | None = None,
        processing_callback: Callable[[str], None] = process_attachment_background,
        cleanup_service_factory: Callable[
            [], TemporaryDocumentService
        ] = get_temporary_document_service,
    ) -> None:
        self.settings = settings
        self._now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )
        self.processing_callback = processing_callback
        self.cleanup_service_factory = cleanup_service_factory

    def recover_once(
        self,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> AttachmentRecoveryResult:
        """Recover processing, cleanup, and expired records within one batch."""

        now = self._utc_now()
        remaining = self.settings.recovery_batch_size
        scanned = 0
        processing_recovered = 0
        cleanup_recovered = 0
        expired_reclaimed = 0
        failures = 0
        cleanup_service: TemporaryDocumentService | None = None

        processing_records = (
            document_repository.list_recoverable_processing_attachments(
                now=now,
                limit=remaining,
            )
        )
        for record in processing_records:
            if stop_requested is not None and stop_requested():
                break
            scanned += 1
            remaining -= 1
            try:
                if record.status in {
                    DocumentStatus.PARSING,
                    DocumentStatus.INDEXING,
                }:
                    interrupted = document_repository.update_document_status(
                        record.id,
                        DocumentStatus.FAILED,
                        expected_status=record.status,
                        error_code=PROCESS_INTERRUPTED,
                        error_message="Attachment processing was interrupted",
                    )
                    if interrupted is None:
                        continue
                self.processing_callback(record.id)
                processing_recovered += 1
            except Exception as exc:
                failures += 1
                current = document_repository.get_document(record.id)
                logger.error(
                    "attachment_recovery_processing_failed document_id=%s "
                    "error_type=%s status=%s",
                    record.id,
                    type(exc).__name__,
                    current.status.value if current is not None else "MISSING",
                )

        if (
            remaining > 0
            and not (stop_requested is not None and stop_requested())
        ):
            cleanup_records = document_repository.list_stale_cleanup_attachments(
                updated_before=now,
                limit=remaining,
            )
            for record in cleanup_records:
                if stop_requested is not None and stop_requested():
                    break
                scanned += 1
                remaining -= 1
                try:
                    if cleanup_service is None:
                        cleanup_service = self.cleanup_service_factory()
                    if cleanup_service.retry_attachment_cleanup(record.id):
                        cleanup_recovered += 1
                except Exception as exc:
                    failures += 1
                    current = document_repository.get_document(record.id)
                    logger.error(
                        "attachment_recovery_cleanup_failed document_id=%s "
                        "error_type=%s status=%s",
                        record.id,
                        type(exc).__name__,
                        current.status.value if current is not None else "PURGED",
                    )

        # Expired attachments are invisible to the accessible-attachment
        # queries, so nothing else ever reclaims their files or vectors.
        if (
            remaining > 0
            and not (stop_requested is not None and stop_requested())
        ):
            expired_records = document_repository.list_expired_attachments(
                now=now,
                limit=remaining,
            )
            for record in expired_records:
                if stop_requested is not None and stop_requested():
                    break
                scanned += 1
                remaining -= 1
                try:
                    if cleanup_service is None:
                        cleanup_service = self.cleanup_service_factory()
                    if cleanup_service.reclaim_expired_attachment(record):
                        expired_reclaimed += 1
                except Exception as exc:
                    failures += 1
                    current = document_repository.get_document(record.id)
                    logger.error(
                        "attachment_recovery_expired_failed document_id=%s "
                        "error_type=%s status=%s",
                        record.id,
                        type(exc).__name__,
                        current.status.value if current is not None else "PURGED",
                    )

        result = AttachmentRecoveryResult(
            scanned=scanned,
            processing_recovered=processing_recovered,
            cleanup_recovered=cleanup_recovered,
            expired_reclaimed=expired_reclaimed,
            failures=failures,
        )
        logger.info(
            "attachment_recovery_completed scanned=%d processing_recovered=%d "
            "cleanup_recovered=%d expired_reclaimed=%d failures=%d",
            result.scanned,
            result.processing_recovered,
            result.cleanup_recovered,
            result.expired_reclaimed,
            result.failures,
        )
        return result

    def _utc_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)


def get_attachment_recovery_service() -> AttachmentRecoveryService:
    """Build the one-shot local recovery service from validated settings."""

    return AttachmentRecoveryService(load_temporary_document_settings())
