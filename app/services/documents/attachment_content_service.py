"""Load parsed attachment text directly into a chat prompt."""

from collections.abc import Callable
from datetime import datetime, timezone

from app.db.models import DocumentStatus
import app.repositories.document_repository as document_repository
from app.services.documents.attachment_retrieval_service import (
    AttachmentEvidence,
    AttachmentNotFoundError,
    AttachmentNotReadyError,
    AttachmentProcessingFailedError,
    AttachmentRetrievalFailedError,
    build_attachment_context,
    normalize_attachment_ids,
)
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedDocumentValidationError,
)
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.settings import load_temporary_document_settings
from app.services.documents.temporary_file_storage import TemporaryFileStorage


class AttachmentContentService:
    """Validate selected attachments and render their parsed text in full."""

    def __init__(
        self,
        parsed_storage: ParsedDocumentStorage | None = None,
        now_provider: Callable[[], datetime] | None = None,
        context_max_chars: int | None = None,
    ) -> None:
        settings = load_temporary_document_settings()
        if parsed_storage is None:
            parsed_storage = ParsedDocumentStorage(
                TemporaryFileStorage(settings.root_path, settings.write_chunk_bytes)
            )
        self.parsed_storage = parsed_storage
        self.context_max_chars = context_max_chars or settings.context_max_chars
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def build_context(
        self,
        *,
        user_id: str,
        session_id: int,
        attachment_ids: list[str],
        max_chars: int | None = None,
    ) -> str:
        selected_ids = normalize_attachment_ids(attachment_ids)
        if not selected_ids:
            return ""

        evidence: list[AttachmentEvidence] = []
        now = self._utc_now()
        for index, document_id in enumerate(selected_ids, start=1):
            document = document_repository.get_owned_attachment(
                document_id=document_id,
                user_id=user_id,
                session_id=session_id,
            )
            if document is None:
                raise AttachmentNotFoundError
            if document.expires_at is None or datetime.fromisoformat(
                document.expires_at.replace("Z", "+00:00")
            ) <= now:
                raise AttachmentNotFoundError
            if document.status in {
                DocumentStatus.UPLOADED,
                DocumentStatus.PARSING,
                DocumentStatus.INDEXING,
            }:
                raise AttachmentNotReadyError
            if document.status is DocumentStatus.FAILED:
                raise AttachmentProcessingFailedError
            if not document.parsed_path:
                raise AttachmentProcessingFailedError

            try:
                parsed = ParsedDocument.from_dict(
                    self.parsed_storage.read_json(document.parsed_path)
                )
                parsed.validate_identity(
                    document_id=document.id,
                    original_filename=document.original_filename,
                    page_count=document.page_count,
                )
            except (ParsedDocumentStorageError, ParsedDocumentValidationError) as exc:
                raise AttachmentProcessingFailedError from exc

            text = "\n\n".join(
                block.text.strip()
                for page in parsed.pages
                for block in page.blocks
                if block.text.strip()
            ).strip()
            if not text:
                raise AttachmentProcessingFailedError
            evidence.append(
                AttachmentEvidence(
                    evidence_id=f"attachment_{index}",
                    document_id=document.id,
                    original_filename=document.original_filename,
                    page_start=1,
                    page_end=max(1, parsed.page_count),
                    text=text,
                    similarity=1.0,
                    locator_unit=parsed.locator_unit,
                )
            )

        context, _ = build_attachment_context(
            evidence,
            max_chars=max_chars or self.context_max_chars,
        )
        if not context:
            raise AttachmentRetrievalFailedError
        return context

    def _utc_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise AttachmentRetrievalFailedError
        return now.astimezone(timezone.utc)
