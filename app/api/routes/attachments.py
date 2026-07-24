"""Temporary PDF attachment API routes."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from app.db.models import DocumentRecord
from app.schemas.documents import AttachmentItem, AttachmentListResponse
from app.services.documents.temporary_document_service import (
    AttachmentCleanupError,
    AttachmentCreationError,
    AttachmentLimitExceeded,
    AttachmentNotFoundError,
    TemporaryDocumentService,
    get_temporary_document_service,
)
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    AttachmentTooLarge,
    InvalidAttachmentFilename,
    UnsupportedAttachmentType,
)


router = APIRouter(tags=["attachments"])

_HANDLED_ATTACHMENT_ERRORS = (
    AttachmentNotFoundError,
    AttachmentLimitExceeded,
    AttachmentTooLarge,
    InvalidAttachmentFilename,
    UnsupportedAttachmentType,
    AttachmentStorageError,
    AttachmentCreationError,
    AttachmentCleanupError,
)


@router.post(
    "/sessions/{session_id}/attachments",
    response_model=AttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    session_id: int,
    user_id: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
    service: Annotated[
        TemporaryDocumentService,
        Depends(get_temporary_document_service),
    ],
) -> AttachmentItem:
    """Upload one temporary PDF using the current user_id identity bridge."""

    try:
        record = service.create_attachment(user_id, session_id, file)
    except _HANDLED_ATTACHMENT_ERRORS as exc:
        _raise_attachment_http_error(exc)
    return _item_from_record(record)


@router.get(
    "/sessions/{session_id}/attachments",
    response_model=AttachmentListResponse,
)
def get_attachments(
    session_id: int,
    user_id: str = Query(..., min_length=1),
    service: TemporaryDocumentService = Depends(get_temporary_document_service),
) -> AttachmentListResponse:
    """List unexpired attachments owned by the current user and session."""

    try:
        records = service.list_attachments(user_id, session_id)
    except _HANDLED_ATTACHMENT_ERRORS as exc:
        _raise_attachment_http_error(exc)
    return AttachmentListResponse(
        session_id=session_id,
        items=[_item_from_record(record) for record in records],
    )


@router.get(
    "/sessions/{session_id}/attachments/{attachment_id}",
    response_model=AttachmentItem,
)
def get_attachment(
    session_id: int,
    attachment_id: str,
    user_id: str = Query(..., min_length=1),
    service: TemporaryDocumentService = Depends(get_temporary_document_service),
) -> AttachmentItem:
    """Get one attachment only after user and session ownership checks."""

    try:
        record = service.get_attachment(attachment_id, user_id, session_id)
    except _HANDLED_ATTACHMENT_ERRORS as exc:
        _raise_attachment_http_error(exc)
    return _item_from_record(record)


@router.delete(
    "/sessions/{session_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    session_id: int,
    attachment_id: str,
    user_id: str = Query(..., min_length=1),
    service: TemporaryDocumentService = Depends(get_temporary_document_service),
) -> Response:
    """Delete attachment files and purge metadata after lifecycle cleanup."""

    try:
        service.delete_attachment(attachment_id, user_id, session_id)
    except _HANDLED_ATTACHMENT_ERRORS as exc:
        _raise_attachment_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _raise_attachment_http_error(error: Exception) -> NoReturn:
    if isinstance(error, AttachmentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "attachment_not_found"},
        ) from error
    if isinstance(error, AttachmentLimitExceeded):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "attachment_limit_reached"},
        ) from error
    if isinstance(error, AttachmentTooLarge):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"error": "attachment_too_large"},
        ) from error
    if isinstance(
        error,
        (InvalidAttachmentFilename, UnsupportedAttachmentType),
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_attachment_type"},
        ) from error
    if isinstance(
        error,
        (
            AttachmentStorageError,
            AttachmentCreationError,
            AttachmentCleanupError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "attachment_storage_error"},
        ) from error
    raise error


def _item_from_record(record: DocumentRecord) -> AttachmentItem:
    return AttachmentItem(
        id=record.id,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at or "",
        error_code=record.error_code,
        error_message=record.error_message,
    )


