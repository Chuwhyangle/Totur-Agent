"""Tutor Agent 单轮聊天的内部上下文对象。"""

from dataclasses import dataclass

from app.db.models import ConversationRecord


@dataclass
class AgentContext:
    """一次聊天请求在进入模型前准备好的上下文。"""

    user_id: str
    session_id: int
    current_message: str
    summary_text: str | None
    recent_history: list[ConversationRecord]
    seed_knowledge_context: str | None = None
