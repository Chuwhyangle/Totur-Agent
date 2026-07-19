"""数据库表名和记录模型。"""

from dataclasses import dataclass


CONVERSATIONS_TABLE = "conversations"
CHAT_SESSIONS_TABLE = "chat_sessions"
SESSION_SUMMARIES_TABLE = "session_summaries"
INTERVIEW_JDS_TABLE = "interview_jds"
DEFAULT_SESSION_TITLE = "默认会话"


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
