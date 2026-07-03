"""Tutor Agent business service."""

import json

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from app.db.models import DEFAULT_SESSION_TITLE, ConversationRecord
from app.repositories.conversation_repository import (
    list_recent_conversations,
    save_conversation,
)
from app.repositories.session_repository import (
    get_or_create_default_session,
    get_session,
    make_title_from_message,
    update_session_title,
)
from app.clients.llm_client import create_llm_client
from app.config import LLMConfig, load_llm_config
from app.schemas.chat import ChatRequest, ChatResponse, TutorReply


# 只加载最近几轮历史，避免 prompt 无限变长。
RECENT_HISTORY_LIMIT = 6
# 某个会话未总结的新消息达到这个数量后，后续阶段再触发滚动摘要。
SUMMARY_TRIGGER_COUNT = 8


class ChatSessionNotFoundError(Exception):
    """聊天请求指定的 session_id 不存在，或不属于当前 user_id。"""


class TutorAgentService:
    """Build prompts, call the model, parse replies, and save history."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
    ) -> None:
        """Initialize configuration and model client."""

        self.config = config or load_llm_config()
        self.client = client or create_llm_client(self.config)

    def chat(self, request: ChatRequest) -> ChatResponse:
        """处理一次聊天请求。"""

        user_id = request.user_id
        message = request.message
        session = self._resolve_session(user_id=user_id, session_id=request.session_id)

        # 多会话模式下，短期记忆只读取当前 session_id 的最近几轮。
        recent_history = list_recent_conversations(
            user_id=user_id,
            session_id=session.id,
            limit=RECENT_HISTORY_LIMIT,
        )
        if not recent_history and session.title == DEFAULT_SESSION_TITLE:
            # 新会话第一条消息发出后，用这条消息生成一个更自然的会话标题。
            update_session_title(session.id, make_title_from_message(message))

        messages = self._build_messages(
            message=message,
            history=recent_history,
        )
        raw_reply = self._call_model(messages)
        reply = self._parse_model_reply(raw_reply)

        reply_json = json.dumps(
            reply.model_dump(),
            ensure_ascii=False,
        )

        save_conversation(
            user_id=user_id,
            message=message,
            reply_json=reply_json,
            session_id=session.id,
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

    def _build_messages(
        self,
        message: str,
        history: list[ConversationRecord],
    ) -> list[ChatCompletionMessageParam]:
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": "你是一个新手友好的后端开发导师。"
            "你必须只返回 JSON，不要返回 Markdown，不要返回解释 JSON 之外的文字。"
            "JSON 必须包含四个字段：answer: 字符串，3 到 6 句话"
            "next_task: 字符串，一个很小的下一步任务"
            "exercise: 字符串，一个小练习"
            "checkpoints: 字符串数组，3 个检查点",
        }
        messages: list[ChatCompletionMessageParam] = [system_msg]

        # 数据库历史是最新在前，发给模型时要改成旧到新。
        for record in reversed(history):
            history_user_msg: ChatCompletionUserMessageParam = {
                "role": "user",
                "content": record.message,
            }
            messages.append(history_user_msg)

            history_answer = self._parse_history_answer(record.reply_json)
            if history_answer:
                # 只放上一轮导师 answer，让历史上下文更简洁。
                history_assistant_msg: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": history_answer,
                }
                messages.append(history_assistant_msg)

        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": message,
        }
        # 当前问题必须放在最后，模型才会把它当成这次要回答的问题。
        messages.append(user_msg)

        return messages

    def _parse_history_answer(self, reply_json: str) -> str | None:
        """Return the saved tutor answer that should become history context."""

        try:
            reply_data = json.loads(reply_json)
        except (json.JSONDecodeError, TypeError):
            return None

        answer = reply_data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None

        return answer

    def _call_model(self, messages: list[ChatCompletionMessageParam]) -> str:
        """Send messages to the model and return the raw text reply."""

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply

    def _parse_model_reply(self, raw_reply: str) -> TutorReply:
        """解析消息，回复消息."""

        cleaned_reply = raw_reply.strip()
        if not cleaned_reply:
            raise RuntimeError("模型回复为空，无法生成导师回复")

        if cleaned_reply.startswith("```json"):
            cleaned_reply = cleaned_reply.removeprefix("```json").removesuffix("```").strip()
        elif cleaned_reply.startswith("```"):
            cleaned_reply = cleaned_reply.removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(cleaned_reply)
            return TutorReply.model_validate(data)
        except (json.JSONDecodeError, ValueError, TypeError):
            return TutorReply(
                answer=cleaned_reply,
                next_task="请把这个问题再具体问一次，或者换一个更小的学习点继续追问。",
                exercise="用一句话写下你刚才最想弄懂的概念。",
                checkpoints=[
                    "系统没有因为模型格式不规范而崩溃",
                    "返回结果仍然包含固定字段",
                    "你知道 fallback 是用来兜底异常输出的",
                ],
            )
