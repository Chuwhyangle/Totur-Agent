"""Database model helpers."""

from dataclasses import dataclass


CONVERSATIONS_TABLE = "conversations"


@dataclass
class ConversationRecord:
    """One row from the conversations table."""

    id: int
    user_id: str
    message: str
    reply_json: str
    created_at: str
