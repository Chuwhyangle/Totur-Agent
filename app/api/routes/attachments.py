"""Temporary conversation attachment API routes."""

from typing import Annotated, NoReturn

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.db.models import DocumentRecord, DocumentStatus
from app.schemas.documents import AttachmentItem, AttachmentListResponse
from app.services.documents.attachment_processing_service import (
    get_attachment_processing_service,
    process_attachment_background,
    process_claimed_attachment_background,
)
from app.services.documents.attachment_retry_service import (
    AttachmentAlreadyProcessing as AttachmentRetryAlreadyProcessing,
    AttachmentRetryNotAllowed,
    AttachmentRetryNotFound,
    AttachmentRetryPreparationError,
    AttachmentRetryService,
    get_attachment_retry_service,
)
from app.services.documents.temporary_document_service import (
    AttachmentCleanupError,
    AttachmentCreationError,
    AttachmentLimitExceeded,
    AttachmentNotFoundError,
    TemporaryDocumentService,
    get_temporary_document_service,
)
from app.services.documents.temporary_file_storage import (
    ArchiveAttachmentNotSupported,
    AttachmentStorageError,
    AttachmentTooLarge,
    InvalidAttachmentFilename,
    LegacyOfficeAttachment,
    UnsupportedAttachmentType,
)


router = APIRouter(tags=["attachments"])

_HANDLED_ATTACHMENT_ERRORS = (
    AttachmentNotFoundError,
    AttachmentLimitExceeded,
    AttachmentTooLarge,
    InvalidAttachmentFilename,
    LegacyOfficeAttachment,
    ArchiveAttachmentNotSupported,
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
    background_tasks: BackgroundTasks,
    user_id: Annotated[str, Form(min_length=1)],
    file: Annotated[UploadFile, File()],
    service: Annotated[
        TemporaryDocumentService,
        Depends(get_temporary_document_service),
    ],
) -> AttachmentItem:
    """Upload one temporary attachment using the current user_id identity bridge."""

    try:
        record = service.create_attachment(user_id, session_id, file)
    except _HANDLED_ATTACHMENT_ERRORS as exc:
        _raise_attachment_http_error(exc)
    # BackgroundTasks is an in-process MVP: it is not durable across restarts and
    # does not coordinate multiple application instances.
    background_tasks.add_task(process_attachment_background, record.id)
    return _item_from_record(record)


@router.post(
    "/sessions/{session_id}/attachments/{attachment_id}/retry",
    response_model=AttachmentItem,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_attachment(
    session_id: int,
    attachment_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Query(..., min_length=1),
    service: AttachmentRetryService = Depends(get_attachment_retry_service),
) -> AttachmentItem:
    """CAS one accessible attachment into PARSING and reschedule it."""

    try:
        claimed = service.claim_retry(attachment_id, user_id, session_id)
    except AttachmentRetryNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "attachment_not_found"},
        ) from exc
    except AttachmentRetryAlreadyProcessing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "attachment_already_processing"},
        ) from exc
    except AttachmentRetryNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "attachment_retry_not_allowed"},
        ) from exc
    except AttachmentRetryPreparationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "attachment_retry_failed"},
        ) from exc

    background_tasks.add_task(
        process_claimed_attachment_background,
        claimed.id,
    )
    return _item_from_record(claimed)


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
    if isinstance(error, LegacyOfficeAttachment):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "attachment_legacy_office_format"},
        ) from error
    if isinstance(error, ArchiveAttachmentNotSupported):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "attachment_archive_not_supported"},
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
        user_safe_message=_user_safe_message(record),
    )


def _user_safe_message(record: DocumentRecord) -> str | None:
    """Map internal parser outcomes to path-safe public messages."""

    if record.status is DocumentStatus.PARTIAL:
        return "The attachment was only partially processed."
    if record.status is not DocumentStatus.FAILED:
        return None

    pdf_messages = {
        "ENCRYPTED_PDF_NOT_SUPPORTED": "当前版本不支持加密 PDF。",
        "PDF_PAGE_LIMIT_EXCEEDED": "PDF 页数超过当前限制。",
        "INVALID_PDF": "PDF 文件损坏或格式无效。",
    }
    if record.error_code in pdf_messages:
        return pdf_messages[record.error_code]
    if record.error_code == "NO_EXTRACTABLE_TEXT":
        if record.mime_type == "application/pdf":
            return "当前版本只支持包含可提取文本层的 PDF，暂不支持扫描件。"
        return "文件中没有可提取的文本内容。"

    messages = {
        "PROCESSING_SERVICE_UNAVAILABLE": (
            "附件处理服务暂时不可用，请稍后重试。"
        ),
        "PROCESS_INTERRUPTED": "附件处理被中断，请重试。",
        "ATTACHMENT_PROCESSING_FAILED": "附件处理失败，请稍后重试。",
        "ATTACHMENT_INDEX_MISSING": "附件索引缺失，请重试处理。",
        "ATTACHMENT_RETRY_PREPARATION_FAILED": (
            "附件重新处理准备失败，请稍后重试。"
        ),
    }
    fallback = (
        "PDF 文档解析失败。"
        if record.mime_type == "application/pdf"
        else "附件解析失败。"
    )
    return messages.get(record.error_code, fallback)
