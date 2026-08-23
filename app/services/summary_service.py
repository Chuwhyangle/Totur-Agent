"""生成和更新会话滚动摘要的服务。"""

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from app.clients.llm_client import create_llm_client
from app.clients.llm_client_pool import get_llm_client
from app.config import LLMConfig, load_llm_config
from app.db.models import ConversationRecord
from app.repositories.summary_repository import (
    count_unsummarized_conversations,
    get_summary,
    list_conversations_after,
    upsert_summary,
)
from app.services.agent.model_registry import resolve_model
from app.services.agent.response_parser import ResponseParser
from app.services.memory_settings import RECENT_HISTORY_LIMIT, SUMMARY_TRIGGER_COUNT


class SummaryService:
    """判断是否需要摘要，并调用模型生成新的会话摘要。"""

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
        response_parser: ResponseParser | None = None,
    ) -> None:
        """保存模型配置；真正调用模型时再创建客户端。"""

        self.config = config
        self.client = client
        self.response_parser = response_parser or ResponseParser()

    def update_summary_if_needed(self, session_id: int) -> bool:
        """如果旧消息足够多，就更新会话摘要；否则不做任何事。"""

        current_summary = get_summary(session_id)
        after_id = current_summary.last_conversation_id if current_summary else 0
        unsummarized_count = count_unsummarized_conversations(session_id, after_id)
        summarizable_count = unsummarized_count - RECENT_HISTORY_LIMIT

        if summarizable_count < SUMMARY_TRIGGER_COUNT:
            return False

        records = list_conversations_after(
            session_id=session_id,
            after_id=after_id,
            limit=summarizable_count,
        )
        if not records:
            return False

        messages = self._build_summary_messages(
            existing_summary=current_summary.summary_text if current_summary else "",
            records=records,
        )
        new_summary = self._call_model(messages).strip()
        if not new_summary:
            raise RuntimeError("摘要模型没有返回内容")

        upsert_summary(
            session_id=session_id,
            summary_text=new_summary,
            last_conversation_id=records[-1].id,
        )
        return True

    def _build_summary_messages(
        self,
        existing_summary: str,
        records: list[ConversationRecord],
    ) -> list[ChatCompletionMessageParam]:
        """把旧摘要和待总结对话整理成摘要模型的输入。"""

        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": (
                "你是 Tutor Agent 的会话摘要器。请把旧摘要和新增对话合并成"
                "一段简洁中文摘要。摘要要保留：用户正在学习的主题、已经"
                "解释过的关键概念、用户卡住或容易混淆的点、导师布置过但"
                "还未完成的任务、后续回答需要延续的上下文。不要编造不"
                "存在的信息，不要输出 Markdown，不要输出 JSON，只输出摘要正文。"
            ),
        }
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": self._format_summary_input(existing_summary, records),
        }

        return [system_msg, user_msg]

    def _format_summary_input(
        self,
        existing_summary: str,
        records: list[ConversationRecord],
    ) -> str:
        """把数据库里的对话记录格式化成可读文本。"""

        lines = [
            "已有摘要：",
            existing_summary.strip() if existing_summary.strip() else "暂无",
            "",
            "新增对话：",
        ]

        for record in records:
            lines.append(f"用户：{record.message}")
            answer = self.response_parser.parse_stored_reply(
                record.reply_json,
                record.reply_format,
            ).answer
            if answer.strip():
                lines.append(f"导师：{answer}")

        lines.extend(
            [
                "",
                "请输出合并后的新摘要。",
            ]
        )
        return "\n".join(lines)

    def _call_model(self, messages: list[ChatCompletionMessageParam]) -> str:
        """调用模型生成摘要正文。"""

        client, model, request_params = self._default_model_runtime()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            **request_params,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("摘要模型没有返回内容")

        return raw_reply

    def _default_model_runtime(self) -> tuple[OpenAI, str, dict]:
        """Resolve the stable default model used by background summaries."""

        if self.config is not None:
            return self._get_client(self.config), self.config.model, {}
        if self.client is not None:
            raise RuntimeError("summary client requires an explicit model config")

        spec = resolve_model()
        request_params = dict(spec.top_level_params)
        if spec.extra_body:
            request_params["extra_body"] = dict(spec.extra_body)
        return get_llm_client(spec.provider), spec.api_model, request_params

    def _get_config(self) -> LLMConfig:
        """懒加载模型配置，方便测试时不读取环境变量。"""

        if self.config is None:
            self.config = load_llm_config()

        return self.config

    def _get_client(self, config: LLMConfig) -> OpenAI:
        """懒加载模型客户端，避免未使用摘要模型时提前连接。"""

        if self.client is None:
            self.client = create_llm_client(config)

        return self.client
