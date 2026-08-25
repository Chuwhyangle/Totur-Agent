"""Knowledge document library API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Response, UploadFile, status

from app.db.models import KnowledgeDocumentRecord, KnowledgeDocumentStatus
import app.repositories.knowledge_document_repository as repository
from app.schemas.knowledge_documents import (
    KnowledgeDocumentItem,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentUploadResponse,
)
from app.services.knowledge_docs.ingestion_service import KnowledgeDocumentIngestionService
from app.services.knowledge_docs.storage import (
    InvalidKnowledgeDocumentFilename,
    KnowledgeDocumentStorage,
    KnowledgeDocumentStorageError,
    KnowledgeDocumentTooLarge,
    UnsupportedKnowledgeDocumentType,
)


router = APIRouter(prefix="/knowledge", tags=["knowledge-documents"])
_service: KnowledgeDocumentIngestionService | None = None


def get_knowledge_ingestion_service() -> KnowledgeDocumentIngestionService:
    global _service
    if _service is None:
        _service = KnowledgeDocumentIngestionService()
    return _service


@router.post(
    "/documents",
    response_model=KnowledgeDocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    response: Response,
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
) -> KnowledgeDocumentUploadResponse:
    service = get_knowledge_ingestion_service()
    try:
        record, duplicate = service.ingest_document(
            user_id=user_id,
            original_filename=file.filename or "",
            media_type=file.content_type or "",
            file_stream=file.file,
        )
        if duplicate:
            response.status_code = status.HTTP_200_OK
        else:
            # Keep the public contract enqueueable; READY records are idempotent on retry.
            background_tasks.add_task(service.reprocess_document, record.id)
        return KnowledgeDocumentUploadResponse(document=_item(record), duplicate=duplicate)
    except UnsupportedKnowledgeDocumentType as exc:
        raise _error(415, "unsupported_document_type", str(exc)) from exc
    except InvalidKnowledgeDocumentFilename as exc:
        raise _error(422, "invalid_document_filename", str(exc)) from exc
    except KnowledgeDocumentTooLarge as exc:
        raise _error(413, "document_too_large", str(exc)) from exc
    except KnowledgeDocumentStorageError as exc:
        raise _error(500, "document_storage_failed", str(exc)) from exc


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_documents(
    user_id: str = Query(..., min_length=1),
    document_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
) -> KnowledgeDocumentListResponse:
    try:
        status_value = KnowledgeDocumentStatus(document_status) if document_status else None
    except ValueError as exc:
        raise _error(422, "invalid_document_status", "Invalid document status") from exc
    records = repository.list_documents(user_id, status_value, limit)
    return KnowledgeDocumentListResponse(items=[_item(record) for record in records])


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentItem)
def get_document(document_id: str, user_id: str = Query(..., min_length=1)) -> KnowledgeDocumentItem:
    record = repository.get_document(document_id)
    if record is None or record.user_id != user_id:
        raise _not_found()
    return _item(record)


@router.post("/documents/{document_id}/retry", response_model=KnowledgeDocumentItem, status_code=status.HTTP_202_ACCEPTED)
def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Query(..., min_length=1),
) -> KnowledgeDocumentItem:
    record = repository.get_document(document_id)
    if record is None or record.user_id != user_id:
        raise _not_found()
    claimed = repository.update_status(
        document_id,
        KnowledgeDocumentStatus.UPLOADED,
        expected_status=KnowledgeDocumentStatus.FAILED,
    )
    if claimed is None:
        raise _error(409, "document_retry_not_allowed", "Document is not retryable")
    service = get_knowledge_ingestion_service()
    background_tasks.add_task(service.reprocess_document, document_id)
    return _item(claimed)


@router.delete("/documents/{document_id}", response_model=KnowledgeDocumentItem)
def delete_document(document_id: str, user_id: str = Query(..., min_length=1)) -> KnowledgeDocumentItem:
    record = repository.get_document(document_id)
    if record is None or record.user_id != user_id:
        raise _not_found()
    claimed = repository.update_status(
        document_id,
        KnowledgeDocumentStatus.DELETING,
        expected_status=KnowledgeDocumentStatus.READY,
    ) or repository.update_status(
        document_id,
        KnowledgeDocumentStatus.DELETING,
        expected_status=KnowledgeDocumentStatus.FAILED,
    )
    if claimed is None:
        raise _error(409, "document_delete_not_allowed", "Document is not deletable")
    service = get_knowledge_ingestion_service()
    service.vector_repository.delete_document(document_id)
    service.storage.delete(record.storage_key)
    deleted = repository.soft_delete(document_id)
    if deleted is None:
        raise _error(500, "document_delete_failed", "Document metadata could not be deleted")
    return _item(deleted)


def _item(record: KnowledgeDocumentRecord) -> KnowledgeDocumentItem:
    return KnowledgeDocumentItem(
        **{field: getattr(record, field) for field in (
            "id", "user_id", "original_filename", "media_type", "size_bytes",
            "storage_key", "file_sha256", "text_sha256", "dedupe_key", "version_no",
            "status", "page_count", "chunk_count", "parser_name", "parser_version",
            "error_code", "error_message", "created_at", "updated_at", "deleted_at",
        )},
        user_safe_message=_user_safe_message(record),
    )


def _user_safe_message(record: KnowledgeDocumentRecord) -> str | None:
    if record.status is not KnowledgeDocumentStatus.FAILED:
        return None
    messages = {
        "INVALID_ENCODING": "Markdown 文件不是有效的 UTF-8 编码。",
        "NO_EXTRACTABLE_TEXT": "文档中没有可提取的文本内容。",
        "DUPLICATE_CONTENT": "文档内容与已有文档重复。",
        "ENCRYPTED_PDF_NOT_SUPPORTED": "当前版本不支持加密 PDF。",
        "NO_EXTRACTABLE_TEXT": "当前版本只支持包含文本层的 PDF。",
    }
    return messages.get(record.error_code or "", "文档处理失败，请稍后重试。")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "document_not_found"})


def _error(code: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "message": message})
