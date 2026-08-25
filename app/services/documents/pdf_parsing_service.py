"""Backward-compatible imports for the renamed attachment parsing service."""

from app.services.documents.attachment_parsing_service import (
    AlreadyParsingError,
    AttachmentParsingExpired,
    AttachmentParsingNotAllowed,
    AttachmentParsingService,
    ParsingAttachmentNotFound,
    PdfParsingCompensationError,
    PdfParsingService,
    PdfParsingServiceError,
)

__all__ = [
    "AlreadyParsingError",
    "AttachmentParsingExpired",
    "AttachmentParsingNotAllowed",
    "AttachmentParsingService",
    "ParsingAttachmentNotFound",
    "PdfParsingCompensationError",
    "PdfParsingService",
    "PdfParsingServiceError",
]
