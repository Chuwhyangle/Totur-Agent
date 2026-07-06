"""把 AgentContext 转换成模型 messages。"""

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from app.services.agent.context import AgentContext
from app.services.agent.personas import (
    Persona,
    build_system_prompt,
    get_persona,
)
from app.services.agent.response_parser import ResponseParser


class PromptBuilder:
    """根据当前上下文构建聊天模型需要的消息列表。"""

    def __init__(self, response_parser: ResponseParser) -> None:
        """保存历史回复解析器。"""

        self.response_parser = response_parser

    def build_messages(
        self,
        context: AgentContext,
        persona: Persona | None = None,
    ) -> list[ChatCompletionMessageParam]:
        """按 system、摘要、最近历史、当前问题的顺序构建 messages。"""

        resolved_persona = persona or get_persona(None)
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": build_system_prompt(resolved_persona),
        }
        messages: list[ChatCompletionMessageParam] = [system_msg]

        if context.summary_text and context.summary_text.strip():
            # 摘要代表较早历史，必须放在最近几轮原文之前。
            summary_msg: ChatCompletionSystemMessageParam = {
                "role": "system",
                "content": (
                    "以下是这个会话较早历史的摘要。它用于帮助你理解上下文，"
                    "但本轮回答仍然要优先回答用户最后的问题。\n"
                    f"{context.summary_text.strip()}"
                ),
            }
            messages.append(summary_msg)

        # 数据库历史是最新在前，发给模型时要改成旧到新。
        for record in reversed(context.recent_history):
            history_user_msg: ChatCompletionUserMessageParam = {
                "role": "user",
                "content": record.message,
            }
            messages.append(history_user_msg)

            history_answer = self.response_parser.parse_history_answer(record.reply_json)
            if history_answer:
                # 只放上一轮导师 answer，让历史上下文更简洁。
                history_assistant_msg: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": history_answer,
                }
                messages.append(history_assistant_msg)

        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": context.current_message,
        }
        # 当前问题必须放在最后，模型才会把它当成这次要回答的问题。
        messages.append(user_msg)

        return messages
