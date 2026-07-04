"""Agent 会话记忆读取与写入。"""

import json

from app.repositories.conversation_repository import (
    list_recent_conversations,
    save_conversation,
)
from app.repositories.summary_repository import get_summary
from app.schemas.chat import TutorReply
from app.services.agent.context import AgentContext
from app.services.memory_settings import RECENT_HISTORY_LIMIT
from app.services.summary_service import SummaryService


class MemoryManager:
    """管理聊天上下文读取、本轮保存和摘要更新。"""

    def __init__(self, summary_service: SummaryService) -> None:
        """保存摘要服务依赖。"""

        self.summary_service = summary_service

    def load_context(
        self,
        user_id: str,
        session_id: int,
        current_message: str,
    ) -> AgentContext:
        """读取当前会话摘要和最近历史，并组装 AgentContext。"""

        # Repository 返回最新在前；PromptBuilder 会在发给模型前改成旧到新。
        recent_history = list_recent_conversations(
            user_id=user_id,
            session_id=session_id,
            limit=RECENT_HISTORY_LIMIT,
        )
        summary = get_summary(session_id)

        return AgentContext(
            user_id=user_id,
            session_id=session_id,
            current_message=current_message,
            summary_text=summary.summary_text if summary else None,
            recent_history=recent_history,
        )

    def save_turn_and_update_summary(
        self,
        user_id: str,
        session_id: int,
        message: str,
        reply: TutorReply,
    ) -> None:
        """保存本轮对话，并尝试触发会话摘要更新。"""

        # 数据库存完整结构化回复，后续构建上下文时只提取 answer 进入 prompt。
        reply_json = json.dumps(
            reply.model_dump(),
            ensure_ascii=False,
        )

        save_conversation(
            user_id=user_id,
            message=message,
            reply_json=reply_json,
            session_id=session_id,
        )
        try:
            # 摘要是辅助记忆能力，失败时不影响本轮聊天结果。
            self.summary_service.update_summary_if_needed(session_id)
        except Exception:
            pass
