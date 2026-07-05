"""Tutor Agent 聊天业务服务。"""

import json
from typing import Any

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
from app.schemas.chat import ChatRequest, ChatResponse, ToolCallTrace, ToolTrace
from app.services.agent.memory_manager import MemoryManager
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.response_parser import ResponseParser
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
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
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
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
        raw_reply, tool_trace = self._run_model_with_optional_tool_call(messages)
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

    def _resolve_session(self, user_id: str, session_id: int | None):
        """确定这次聊天要写入哪个会话。"""

        if session_id is None:
            # 兼容旧版前端：不传 session_id 时仍然使用默认会话。
            return get_or_create_default_session(user_id)

        session = get_session(session_id)
        if session is None or session.user_id != user_id:
            raise ChatSessionNotFoundError

        return session

    def _run_model_with_optional_tool_call(
        self,
        messages: list[ChatCompletionMessageParam],
    ) -> tuple[str, ToolTrace]:
        """执行临时的一轮 function calling；后续会演进为 ReAct 编排。"""

        first_message = self._call_model_with_tools(messages)
        tool_calls = self._message_tool_calls(first_message)

        if not tool_calls:
            raw_reply = self._message_content(first_message)
            if not raw_reply:
                raise RuntimeError("模型没有返回内容")

            return raw_reply, ToolTrace(used=False, calls=[])

        messages_with_tool_results, tool_call_traces = self._build_messages_with_tool_results(
            messages=messages,
            first_message=first_message,
            tool_calls=tool_calls,
        )

        return self._call_model(messages_with_tool_results), ToolTrace(
            used=True,
            calls=tool_call_traces,
        )

    def _call_model_with_tools(self, messages: list[ChatCompletionMessageParam]):
        """第一次调用模型时提供工具 schema，让模型选择是否调用工具。"""

        if "_call_model" in self.__dict__:
            # 兼容旧测试：如果测试替换了 _call_model，就沿用旧的文本返回路径。
            return {
                "content": self._call_model(messages),
                "tool_calls": [],
            }

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=self.tool_registry.get_tools_schema(),
            tool_choice="auto",
        )

        return completion.choices[0].message

    def _build_messages_with_tool_results(
        self,
        messages: list[ChatCompletionMessageParam],
        first_message,
        tool_calls: list[Any],
    ) -> tuple[list[ChatCompletionMessageParam], list[ToolCallTrace]]:
        """把模型 tool call 和工具执行结果追加到第二次模型输入里。"""

        tool_messages: list[dict[str, Any]] = [
            *messages,
            self._assistant_tool_call_message(first_message, tool_calls),
        ]
        traces: list[ToolCallTrace] = []

        for index, tool_call in enumerate(tool_calls):
            tool_name = self._tool_call_name(tool_call)
            tool_arguments = self._tool_call_arguments(tool_call)
            tool_result = self.tool_executor.execute(
                tool_name,
                tool_arguments,
            )
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": self._tool_call_id(tool_call, index),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
            traces.append(
                self._tool_call_trace(
                    name=tool_name,
                    arguments=tool_arguments,
                    result=tool_result,
                )
            )

        return tool_messages, traces

    def _tool_call_trace(
        self,
        name: str,
        arguments: str,
        result: dict[str, Any],
    ) -> ToolCallTrace:
        summary = result.get("summary") if isinstance(result, dict) else None
        items = result.get("items") if isinstance(result, dict) else None
        top_titles = [
            str(item["title"])
            for item in (items or [])[:3]
            if isinstance(item, dict) and item.get("title")
        ]

        return ToolCallTrace(
            name=name,
            arguments=self._trace_arguments(arguments),
            ok=bool(result.get("ok")) if isinstance(result, dict) else False,
            returned_count=(
                summary.get("returned_count")
                if isinstance(summary, dict)
                else None
            ),
            top_titles=top_titles,
            result_preview=self._tool_result_preview(items),
            error=result.get("error") if isinstance(result, dict) else "invalid_result",
        )

    def _tool_result_preview(self, items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        preview = []
        for item in items[:3]:
            if not isinstance(item, dict) or not item.get("title"):
                continue

            preview.append(
                {
                    "title": str(item["title"]),
                    "match_score": self._optional_int(item.get("match_score")),
                    "matched_fields": self._trace_string_list(
                        item.get("matched_fields")
                    ),
                    "core_skills": self._trace_string_list(item.get("core_skills")),
                    "keywords": self._trace_string_list(item.get("keywords")),
                    "interview_focus": self._trace_string_list(
                        item.get("interview_focus")
                    ),
                    "raw_text_excerpt": str(item.get("raw_text_excerpt") or ""),
                }
            )

        return preview

    def _optional_int(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _trace_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        return [item for item in value if isinstance(item, str)]

    def _trace_arguments(self, arguments: str) -> dict[str, Any]:
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        return parsed

    def _assistant_tool_call_message(
        self,
        first_message,
        tool_calls: list[Any],
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                self._tool_call_payload(tool_call, index)
                for index, tool_call in enumerate(tool_calls)
            ],
        }
        content = self._message_content(first_message)
        if content:
            message["content"] = content

        return message

    def _message_content(self, message) -> str | None:
        if isinstance(message, str):
            return message

        if isinstance(message, dict):
            return message.get("content")

        return getattr(message, "content", None)

    def _message_tool_calls(self, message) -> list[Any]:
        if isinstance(message, dict):
            return message.get("tool_calls") or []

        return getattr(message, "tool_calls", None) or []

    def _tool_call_payload(self, tool_call, index: int) -> dict[str, Any]:
        return {
            "id": self._tool_call_id(tool_call, index),
            "type": "function",
            "function": {
                "name": self._tool_call_name(tool_call),
                "arguments": self._tool_call_arguments(tool_call),
            },
        }

    def _tool_call_id(self, tool_call, index: int) -> str:
        if isinstance(tool_call, dict):
            return str(tool_call.get("id") or f"tool_call_{index}")

        return str(getattr(tool_call, "id", None) or f"tool_call_{index}")

    def _tool_call_name(self, tool_call) -> str:
        function = self._tool_call_function(tool_call)

        if isinstance(function, dict):
            return str(function.get("name") or "")

        return str(getattr(function, "name", "") or "")

    def _tool_call_arguments(self, tool_call) -> str:
        function = self._tool_call_function(tool_call)

        if isinstance(function, dict):
            return str(function.get("arguments") or "{}")

        return str(getattr(function, "arguments", None) or "{}")

    def _tool_call_function(self, tool_call):
        if isinstance(tool_call, dict):
            return tool_call.get("function") or {}

        return getattr(tool_call, "function", None)

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
