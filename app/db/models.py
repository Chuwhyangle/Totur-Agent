"""Database model helpers."""

from dataclasses import dataclass


CONVERSATIONS_TABLE = "conversations"
CHAT_SESSIONS_TABLE = "chat_sessions"
DEFAULT_SESSION_TITLE = "默认会话"


@dataclass
class ChatSessionRecord:
    """One row from the chat_sessions table."""

    id: int
    user_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass
class ConversationRecord:
    """One row from the conversations table."""

    id: int
    session_id: int | None
    user_id: str
    message: str
    reply_json: str
    created_at: str
