"""Tutor Agent 聊天业务服务。"""

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
)
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
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.response_parser import ResponseParser
from app.services.summary_service import SummaryService


class ChatSessionNotFoundError(Exception):
    """聊天请求指定的 session_id 不存在，或不属于当前 user_id。"""


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

    def chat(self, request: ChatRequest) -> ChatResponse:
        """处理一次聊天请求。"""

        user_id = request.user_id
        message = request.message
        session = self._resolve_session(user_id=user_id, session_id=request.session_id)

        # 先准备模型上下文；具体怎么读历史和摘要交给 MemoryManager。
        context = self.memory_manager.load_context(
            user_id=user_id,
            session_id=session.id,
            current_message=message,
        )
        if not context.recent_history and session.title == DEFAULT_SESSION_TITLE:
            # 新会话第一条消息发出后，用这条消息生成一个更自然的会话标题。
            update_session_title(session.id, make_title_from_message(message))

        messages = self.prompt_builder.build_messages(context)
        raw_reply = self._call_model(messages)
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
        )

    def _resolve_session(self, user_id: str, session_id: int | None):
        """确定这次聊天要写入哪个会话。"""

        if session_id is None:
            # 兼容旧版前端：不传 session_id 时仍然使用默认会话。
            return get_or_create_default_session(user_id)

        session = get_session(session_id)
        if session is None or session.user_id != user_id:
            raise ChatSessionNotFoundError

        return session

    def _call_model(self, messages: list[ChatCompletionMessageParam]) -> str:
        """把 messages 发送给模型，并返回原始文本回复。"""

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply
