"""Public schemas for the knowledge document library."""

from pydantic import BaseModel

from app.db.models import KnowledgeDocumentStatus


class KnowledgeDocumentItem(BaseModel):
    id: str
    user_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    storage_key: str | None
    file_sha256: str
    text_sha256: str | None
    dedupe_key: str | None
    version_no: int
    status: KnowledgeDocumentStatus
    page_count: int | None
    chunk_count: int | None
    parser_name: str | None
    parser_version: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None
    user_safe_message: str | None = None


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentItem]


class KnowledgeDocumentUploadResponse(BaseModel):
    document: KnowledgeDocumentItem
    duplicate: bool
