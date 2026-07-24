"""数据库表名和记录模型。"""

from dataclasses import dataclass
from enum import Enum


CONVERSATIONS_TABLE = "conversations"
CHAT_SESSIONS_TABLE = "chat_sessions"
SESSION_SUMMARIES_TABLE = "session_summaries"
INTERVIEW_JDS_TABLE = "interview_jds"
DOCUMENTS_TABLE = "documents"
DEFAULT_SESSION_TITLE = "默认会话"


class DocumentScope(str, Enum):
    """Isolation scope for a stored document."""

    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    ATTACHMENT = "ATTACHMENT"


class DocumentStatus(str, Enum):
    """Processing lifecycle for a document."""

    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class DocumentDomainError(ValueError):
    """Base exception for document domain rule violations."""


class InvalidDocumentRecord(DocumentDomainError):
    """A document record violates its scope, status, or field constraints."""


class InvalidDocumentStatusTransition(DocumentDomainError):
    """A requested document status transition is not allowed."""


ALLOWED_DOCUMENT_STATUS_TRANSITIONS = {
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.PARSING}),
    DocumentStatus.PARSING: frozenset(
        {
            DocumentStatus.READY,
            DocumentStatus.PARTIAL,
            DocumentStatus.FAILED,
        }
    ),
    DocumentStatus.FAILED: frozenset(
        {DocumentStatus.PARSING, DocumentStatus.DELETING}
    ),
    DocumentStatus.READY: frozenset({DocumentStatus.DELETING}),
    DocumentStatus.PARTIAL: frozenset({DocumentStatus.DELETING}),
    DocumentStatus.DELETING: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.DELETED: frozenset(),
}


def validate_document_status_transition(
    current_status: DocumentStatus | str,
    new_status: DocumentStatus | str,
) -> None:
    """Raise a domain exception when a lifecycle transition is not allowed."""

    try:
        current = DocumentStatus(current_status)
        target = DocumentStatus(new_status)
    except ValueError as exc:
        raise InvalidDocumentRecord(f"Unknown document status: {exc}") from exc

    if target not in ALLOWED_DOCUMENT_STATUS_TRANSITIONS[current]:
        raise InvalidDocumentStatusTransition(
            f"Document status cannot transition from {current.value} "
            f"to {target.value}"
        )


@dataclass
class ChatSessionRecord:
    """chat_sessions 表中的一行记录。"""

    id: int
    user_id: str
    title: str
    persona_id: str
    created_at: str
    updated_at: str
    subject: str | None = None


@dataclass
class ConversationRecord:
    """conversations 表中的一行记录。"""

    id: int
    session_id: int | None
    user_id: str
    message: str
    reply_json: str
    created_at: str


@dataclass
class SessionSummaryRecord:
    """session_summaries 表中的一行摘要记录。"""

    id: int
    session_id: int
    summary_text: str
    last_conversation_id: int
    created_at: str
    updated_at: str


@dataclass
class InterviewJDRecord:
    """interview_jds 表中的一行岗位 JD 记录。"""

    id: int
    user_id: str
    title: str
    role_family: str | None
    seniority: str | None
    target_graduation_years: list[str]
    raw_text: str
    responsibilities: list[str]
    must_have: list[str]
    core_skills: list[str]
    preferred_skills: list[str]
    bonus_skills: list[str]
    keywords: list[str]
    interview_focus: list[str]
    created_at: str
    updated_at: str


@dataclass
class DocumentRecord:
    """Document metadata stored in SQLite; raw document text is excluded."""

    id: str
    scope: DocumentScope
    user_id: str | None
    session_id: int | None
    message_id: int | None
    original_filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    parsed_path: str | None
    content_hash: str | None
    status: DocumentStatus
    parser_name: str | None
    parser_version: str | None
    page_count: int | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    expires_at: str | None

    def __post_init__(self) -> None:
        try:
            self.scope = DocumentScope(self.scope)
            self.status = DocumentStatus(self.status)
        except ValueError as exc:
            raise InvalidDocumentRecord(str(exc)) from exc

        if not self.id:
            raise InvalidDocumentRecord("document id must not be empty")
        if self.size_bytes < 0:
            raise InvalidDocumentRecord("size_bytes must not be negative")
        if self.page_count is not None and self.page_count < 0:
            raise InvalidDocumentRecord("page_count must not be negative")

        if self.scope is DocumentScope.ATTACHMENT:
            if not self.user_id or self.session_id is None or not self.expires_at:
                raise InvalidDocumentRecord(
                    "ATTACHMENT requires user_id, session_id, and expires_at"
                )
        elif self.scope is DocumentScope.PRIVATE:
            if not self.user_id or self.session_id is not None:
                raise InvalidDocumentRecord(
                    "PRIVATE requires user_id and forbids session_id"
                )
        elif (
            self.user_id is not None
            or self.session_id is not None
            or self.expires_at is not None
        ):
            raise InvalidDocumentRecord(
                "INTERNAL forbids user_id, session_id, and expires_at"
            )

        if self.status is DocumentStatus.FAILED and not (
            self.error_code and self.error_code.strip()
        ):
            raise InvalidDocumentRecord(
                "FAILED documents require a stable error_code"
            )
