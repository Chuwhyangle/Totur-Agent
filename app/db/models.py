"""数据库表名和记录模型。"""

from dataclasses import dataclass
from enum import Enum


CONVERSATIONS_TABLE = "conversations"
CHAT_SESSIONS_TABLE = "chat_sessions"
SESSION_SUMMARIES_TABLE = "session_summaries"
INTERVIEW_JDS_TABLE = "interview_jds"
PUBLIC_JOB_DESCRIPTIONS_TABLE = "public_job_descriptions"
DOCUMENTS_TABLE = "documents"
JOURNAL_ENTRIES_TABLE = "journal_entries"
WORKSPACES_TABLE = "workspaces"
CUSTOM_PERSONAS_TABLE = "custom_personas"
WORKSPACE_ASSETS_TABLE = "workspace_assets"
TASKS_TABLE = "tasks"
TASK_STEPS_TABLE = "task_steps"
TASK_ASSET_REFS_TABLE = "task_asset_refs"
ARTIFACTS_TABLE = "artifacts"
ARTIFACT_SOURCES_TABLE = "artifact_sources"
DEFAULT_SESSION_TITLE = "默认会话"


class WorkspaceStatus(str, Enum):
    """Lifecycle state of a long-lived Workspace."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class WorkspaceAssetStatus(str, Enum):
    """Reserved lifecycle states for future Workspace assets."""

    STAGING = "STAGING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class WorkspaceTaskStatus(str, Enum):
    """Reserved lifecycle states for future Workspace tasks."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkspaceTaskStepStatus(str, Enum):
    """Reserved lifecycle states for future task steps."""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ArtifactStatus(str, Enum):
    """Reserved lifecycle states for future Workspace artifacts."""

    CREATING = "CREATING"
    READY = "READY"
    FAILED = "FAILED"


class DocumentScope(str, Enum):
    """Isolation scope for a stored document."""

    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    ATTACHMENT = "ATTACHMENT"


class DocumentStatus(str, Enum):
    """Processing lifecycle for a document."""

    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    INDEXING = "INDEXING"
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


class DocumentPurgeNotAllowedError(DocumentDomainError):
    """A document record cannot be purged before reaching DELETED."""


ALLOWED_DOCUMENT_STATUS_TRANSITIONS = {
    DocumentStatus.UPLOADED: frozenset(
        {
            DocumentStatus.PARSING,
            DocumentStatus.FAILED,
            DocumentStatus.DELETING,
        }
    ),
    DocumentStatus.PARSING: frozenset(
        {
            DocumentStatus.INDEXING,
            DocumentStatus.FAILED,
            DocumentStatus.DELETING,
        }
    ),
    DocumentStatus.INDEXING: frozenset(
        {
            DocumentStatus.READY,
            DocumentStatus.PARTIAL,
            DocumentStatus.FAILED,
            DocumentStatus.DELETING,
        }
    ),
    DocumentStatus.FAILED: frozenset(
        {DocumentStatus.PARSING, DocumentStatus.DELETING}
    ),
    DocumentStatus.READY: frozenset(
        {DocumentStatus.FAILED, DocumentStatus.DELETING}
    ),
    DocumentStatus.PARTIAL: frozenset(
        {DocumentStatus.FAILED, DocumentStatus.DELETING}
    ),
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
    workspace_id: str | None = None


@dataclass
class WorkspaceRecord:
    """workspaces 表中的一行记录。"""

    id: str
    user_id: str
    name: str
    description: str | None
    status: WorkspaceStatus
    created_at: str
    updated_at: str
    archived_at: str | None = None
    agent_instructions: str | None = None
    agent_instructions_version: int = 0

    def __post_init__(self) -> None:
        self.status = WorkspaceStatus(self.status)


@dataclass
class CustomPersonaRecord:
    """custom_personas 表中的一行记录。"""

    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    status: str
    created_at: str
    updated_at: str


@dataclass
class WorkspaceAssetRecord:
    """workspace_assets 表中的一行记录。"""

    id: str
    workspace_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    storage_key: str | None
    parsed_storage_key: str | None
    content_hash: str
    dedupe_key: str | None
    status: WorkspaceAssetStatus
    parser_name: str | None
    parser_version: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None = None

    def __post_init__(self) -> None:
        self.status = WorkspaceAssetStatus(self.status)


@dataclass
class WorkspaceTaskRecord:
    """tasks 表中的一行记录。"""

    id: str
    workspace_id: str
    session_id: int
    trace_id: str
    goal: str
    status: WorkspaceTaskStatus
    warning_count: int
    error_code: str | None
    started_at: str
    finished_at: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        self.status = WorkspaceTaskStatus(self.status)


@dataclass
class WorkspaceTaskStepRecord:
    """task_steps 表中的一行记录。"""

    id: int
    task_id: str
    sequence_no: int
    tool_call_id: str
    step_type: str
    tool_name: str
    status: WorkspaceTaskStepStatus
    input_summary: str | None
    output_summary: str | None
    error_code: str | None
    started_at: str
    finished_at: str | None
    created_at: str

    def __post_init__(self) -> None:
        self.status = WorkspaceTaskStepStatus(self.status)


@dataclass
class TaskAssetRefRecord:
    """task_asset_refs 表中的一行记录。"""

    task_id: str
    asset_id: str
    first_step_id: int
    created_at: str


@dataclass
class ArtifactRecord:
    """artifacts 表中的一行记录。"""

    id: str
    workspace_id: str
    task_id: str
    created_by_step_id: int
    artifact_series_id: str
    supersedes_artifact_id: str | None
    version_number: int
    title: str
    media_type: str
    storage_key: str | None
    size_bytes: int | None
    content_hash: str | None
    creation_key: str
    status: ArtifactStatus
    error_code: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None = None

    def __post_init__(self) -> None:
        self.status = ArtifactStatus(self.status)


@dataclass
class ArtifactSourceRecord:
    """artifact_sources 表中的一行记录。"""

    artifact_id: str
    asset_id: str
    created_at: str


@dataclass
class ConversationRecord:
    """conversations 表中的一行记录。"""

    id: int
    session_id: int | None
    user_id: str
    message: str
    reply_json: str
    created_at: str
    reply_format: str = "json_v1"


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


@dataclass(frozen=True)
class PublicJDRecord:
    """One structured public JD imported from ``corpus/JD``."""

    jd_id: str
    fingerprint: str
    category: str
    source_path: str
    source_url: str
    title: str
    company: str
    salary_raw: str
    salary_min_k: float
    salary_max_k: float
    education: str
    recruitment_count: str
    major: str
    region: str
    province: str
    source_updated_at: str
    industry: str
    company_type: str
    company_size: str
    relevance: str
    relevance_score: int
    function_category: str
    keywords: tuple[str, ...]
    duplicate_count: int
    row_sha256: str
    parent_sha256: str


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
    # Relative storage key under the temporary document root, never absolute.
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

        if self.status in {
            DocumentStatus.INDEXING,
            DocumentStatus.READY,
            DocumentStatus.PARTIAL,
        }:
            if not self.parsed_path or not self.parsed_path.strip():
                raise InvalidDocumentRecord(
                    f"{self.status.value} documents require parsed_path"
                )
            if self.page_count is None or self.page_count <= 0:
                raise InvalidDocumentRecord(
                    f"{self.status.value} documents require page_count > 0"
                )

        if self.status is DocumentStatus.INDEXING and (
            not self.parser_name
            or not self.parser_name.strip()
            or not self.parser_version
            or not self.parser_version.strip()
        ):
            raise InvalidDocumentRecord(
                "INDEXING documents require parser_name and parser_version"
            )

        if self.status in {DocumentStatus.FAILED, DocumentStatus.PARTIAL} and not (
            self.error_code and self.error_code.strip()
        ):
            raise InvalidDocumentRecord(
                f"{self.status.value} documents require a stable error_code"
            )


@dataclass
class JournalEntryRecord:
    """journal_entries 表中的一行日记记录。"""

    id: int
    session_id: int | None
    persona_id: str
    title: str
    content: str
    tags: str
    entry_date: str
    created_at: str
    updated_at: str
