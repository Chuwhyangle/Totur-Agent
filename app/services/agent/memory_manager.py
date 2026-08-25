"""Agent 会话记忆读取与写入。"""

from app.repositories.conversation_repository import (
    list_recent_conversations,
    save_conversation,
)
from app.repositories.learning_progress_repository import list_learning_progress
from app.repositories.summary_repository import get_summary
from app.schemas.chat import TutorReply
from app.services.agent.context import AgentContext
from app.services.agent.response_parser import REPLY_FORMAT_MARKDOWN_V2
from app.services.memory_settings import RECENT_HISTORY_LIMIT
from app.services.summary_service import SummaryService
from app.services.workspaces.workspace_service import WorkspaceService


class MemoryManager:
    """管理聊天上下文读取、本轮保存和摘要更新。"""

    def __init__(self, summary_service: SummaryService) -> None:
        """保存摘要服务依赖。"""

        self.summary_service = summary_service
        self.workspace_service = WorkspaceService()

    def load_context(
        self,
        user_id: str,
        session_id: int,
        current_message: str,
        learning_subject: str | None = None,
        progress_update_requested: bool = False,
    ) -> AgentContext:
        """读取当前会话摘要和最近历史，并组装 AgentContext。"""

        # Repository 返回最新在前；PromptBuilder 会在发给模型前改成旧到新。
        recent_history = list_recent_conversations(
            user_id=user_id,
            session_id=session_id,
            limit=RECENT_HISTORY_LIMIT,
        )
        summary = get_summary(session_id)
        learning_progress = (
            list_learning_progress(user_id=user_id, subject=learning_subject, limit=50)
            if learning_subject
            else []
        )

        return AgentContext(
            user_id=user_id,
            session_id=session_id,
            current_message=current_message,
            summary_text=summary.summary_text if summary else None,
            recent_history=recent_history,
            learning_progress=learning_progress,
            progress_update_requested=progress_update_requested,
        )

    def save_turn_and_update_summary(
        self,
        user_id: str,
        session_id: int,
        message: str,
        reply: TutorReply,
    ) -> None:
        """保存本轮对话，并尝试触发会话摘要更新。"""

        # markdown_v2：reply_json 直接存 Markdown 正文；
        # json_v1 的旧记录仍存五字段 JSON 信封。读取时按 reply_format 显式分发。
        reply_json = reply.answer

        def validate_workspace_before_insert(connection) -> None:
            session = self._get_session_for_write(session_id, connection)
            if session.workspace_id is not None:
                self.workspace_service.ensure_enabled(session.workspace_id)
                self.workspace_service.ensure_active_workspace(
                    session.workspace_id,
                    conn=connection,
                    for_update=True,
                )

        save_conversation(
            user_id=user_id,
            message=message,
            reply_json=reply_json,
            session_id=session_id,
            reply_format=REPLY_FORMAT_MARKDOWN_V2,
            before_insert=validate_workspace_before_insert,
        )
        try:
            # 摘要是辅助记忆能力，失败时不影响本轮聊天结果。
            self.summary_service.update_summary_if_needed(session_id)
        except Exception:
            pass

    @staticmethod
    def _get_session_for_write(session_id: int, connection):
        from app.repositories.session_repository import get_session_for_update

        session = get_session_for_update(session_id, conn=connection)
        if session is None:
            raise RuntimeError("Session not found while saving conversation")
        return session
