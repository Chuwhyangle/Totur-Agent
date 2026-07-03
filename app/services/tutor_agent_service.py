"""Tutor Agent business service."""

import json

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from app.repositories.conversation_repository import save_conversation
from app.clients.llm_client import create_llm_client
from app.config import LLMConfig, load_llm_config
from app.schemas.chat import ChatRequest, ChatResponse, TutorReply


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
        """Handle one chat request."""

        user_id = request.user_id
        message = request.message

        messages = self._build_messages(message)
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
        )

        return ChatResponse(
            user_id=user_id,
            message=message,
            reply=reply,
        )

    def _build_messages(self, message: str) -> list[ChatCompletionMessageParam]:
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": "你是一个新手友好的后端开发导师。"
            "你必须只返回 JSON，不要返回 Markdown，不要返回解释 JSON 之外的文字。"
            "JSON 必须包含四个字段：answer: 字符串，3 到 6 句话"
            "next_task: 字符串，一个很小的下一步任务"
            "exercise: 字符串，一个小练习"
            "checkpoints: 字符串数组，3 个检查点",
        }
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": message,
        }
        return [system_msg, user_msg]

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
