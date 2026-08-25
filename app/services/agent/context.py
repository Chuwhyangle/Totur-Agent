"""Tutor Agent 单轮聊天的内部上下文对象。"""

from dataclasses import dataclass, field

from app.db.models import ConversationRecord, LearningProgressRecord


@dataclass
class AgentContext:
    """一次聊天请求在进入模型前准备好的上下文。"""

    user_id: str
    session_id: int
    current_message: str
    summary_text: str | None
    recent_history: list[ConversationRecord]
    learning_progress: list[LearningProgressRecord] = field(default_factory=list)
    progress_update_requested: bool = False
    seed_knowledge_context: str | None = None
    attachment_context: str | None = None
    private_jd_context: str | None = None
    workspace_agent_instructions: str | None = None
    workspace_agent_instructions_version: int | None = None
