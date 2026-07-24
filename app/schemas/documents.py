"""Safe API response schemas for temporary conversation attachments."""

from pydantic import BaseModel

from app.db.models import DocumentStatus


class AttachmentItem(BaseModel):
    """Public attachment metadata with all storage internals excluded."""

    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    created_at: str
    expires_at: str
    error_code: str | None = None
    error_message: str | None = None


class AttachmentListResponse(BaseModel):
    """Public attachments belonging to one chat session."""

    session_id: int
    items: list[AttachmentItem]
