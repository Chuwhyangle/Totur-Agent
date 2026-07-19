"""Tutor Agent 聊天业务服务。"""

from collections.abc import Callable

from openai import OpenAI
from app.db.models import DEFAULT_SESSION_TITLE
from app.repositories.session_repository import (
    get_or_create_default_session,
    get_session,
    make_title_from_message,
    update_session_title,
)
from app.clients.llm_client import create_llm_client
from app.config import LLMConfig, load_llm_config
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent.memory_manager import MemoryManager
from app.services.agent.personas import (
    DEFAULT_PERSONA_ID,
    get_persona,
)
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.react_orchestrator import ReactOrchestrator
from app.services.agent.response_parser import ResponseParser
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.rag_seed_context import retrieve_seed_knowledge_context
from app.services.rag_settings import ENABLE_RAG_SEED_CONTEXT
from app.services.summary_service import SummaryService


class ChatSessionNotFoundError(Exception):
    """聊天请求指定的 session_id 不存在，或不属于当前 user_id。"""


class SessionPersonaMismatchError(Exception):
    """聊天请求试图用不同 persona_id 切换一个已绑定会话。"""

    def __init__(
        self,
        session_id: int,
        session_persona_id: str,
        request_persona_id: str,
    ) -> None:
        """保存冲突双方，方便 API 返回可读错误。"""

        self.session_id = session_id
        self.session_persona_id = session_persona_id
        self.request_persona_id = request_persona_id
        super().__init__(
            f"session {session_id} is bound to {session_persona_id}, "
            f"not {request_persona_id}"
        )


class TutorAgentService:
    """编排聊天流程：构建 prompt、调用模型、解析回复并保存历史。"""

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
        summary_service: SummaryService | None = None,
        response_parser: ResponseParser | None = None,
        prompt_builder: PromptBuilder | None = None,
        memory_manager: MemoryManager | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        react_orchestrator: ReactOrchestrator | None = None,
        seed_context_enabled: bool = ENABLE_RAG_SEED_CONTEXT,
        seed_context_provider: Callable[[str], str | None] | None = None,
    ) -> None:
        """初始化模型配置、模型客户端和 Agent 辅助组件。"""

        self.config = config or load_llm_config()
        self.client = client or create_llm_client(self.config)
        self.summary_service = summary_service or SummaryService(
            config=self.config,
            client=self.client,
        )
        self.response_parser = response_parser or ResponseParser()
        self.prompt_builder = prompt_builder or PromptBuilder(self.response_parser)
        self.memory_manager = memory_manager or MemoryManager(self.summary_service)
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = tool_executor or ToolExecutor(self.tool_registry)
        self.react_orchestrator = react_orchestrator or ReactOrchestrator(
            config=self.config,
            client=self.client,
            tool_registry=self.tool_registry,
            tool_executor=self.tool_executor,
        )
        self.seed_context_enabled = seed_context_enabled
        self.seed_context_provider = seed_context_provider or retrieve_seed_knowledge_context

    def chat(self, request: ChatRequest) -> ChatResponse:
        """处理一次聊天请求。"""

        user_id = request.user_id
        message = request.message
        session = self._resolve_session(
            user_id=user_id,
            session_id=request.session_id,
            request_persona_id=request.persona_id,
        )
        persona = get_persona(session.persona_id)
        set_defaults = getattr(self.tool_executor, "set_default_tool_kwargs", None)
        if callable(set_defaults):
            set_defaults({"search_learning_notes": {"subject": session.subject}})

        # 先准备模型上下文；具体怎么读历史和摘要交给 MemoryManager。
        context = self.memory_manager.load_context(
            user_id=user_id,
            session_id=session.id,
            current_message=message,
        )
        if self.seed_context_enabled:
            context.seed_knowledge_context = self.seed_context_provider(message)

        if not context.recent_history and session.title == DEFAULT_SESSION_TITLE:
            # 新会话第一条消息发出后，用这条消息生成一个更自然的会话标题。
            update_session_title(session.id, make_title_from_message(message))

        messages = self.prompt_builder.build_messages(context, persona=persona)
        raw_reply, tool_trace = self.react_orchestrator.run(messages)
        reply = self.response_parser.parse_model_reply(raw_reply)

        # 模型回复已经结构化后，再统一保存本轮对话并尝试推进摘要。
        self.memory_manager.save_turn_and_update_summary(
            user_id=user_id,
            session_id=session.id,
            message=message,
            reply=reply,
        )

        return ChatResponse(
            user_id=user_id,
            session_id=session.id,
            message=message,
            reply=reply,
            tool_trace=tool_trace,
        )

    def _resolve_session(
        self,
        user_id: str,
        session_id: int | None,
        request_persona_id: str | None = None,
    ):
        """确定这次聊天要写入哪个会话。"""

        request_persona = (
            get_persona(request_persona_id) if request_persona_id is not None else None
        )
        if session_id is None:
            # 兼容旧版前端：不传 session_id 时仍然使用默认会话，但默认会话按 persona 隔离。
            return get_or_create_default_session(
                user_id,
                persona_id=request_persona.persona_id
                if request_persona is not None
                else DEFAULT_PERSONA_ID,
            )

        session = get_session(session_id)
        if session is None or session.user_id != user_id:
            raise ChatSessionNotFoundError

        if (
            request_persona is not None
            and request_persona.persona_id != session.persona_id
        ):
            raise SessionPersonaMismatchError(
                session_id=session.id,
                session_persona_id=session.persona_id,
                request_persona_id=request_persona.persona_id,
            )

        return session
