"""学习辅导 Agent 的业务服务。

这个文件负责：
1. 承接 /chat 路由传进来的 ChatRequest。
2. 组织导师回复的业务流程。
3. 后续在这里调用大模型、整合上下文、生成结构化回复。

这个文件不负责：
1. 定义 HTTP 路径，例如 /chat。
2. 创建 FastAPI 应用。
3. 直接处理前端页面。

学习重点：
当路由文件里的函数越来越长时，就把“怎么处理业务”拆进 service。
这样 route 更像入口，service 更像大脑。
"""
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
    """学习辅导 Agent 的业务服务类。

    阶段 4 里，你会把“调用模型”这件事放进来。
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
    ) -> None:
        """初始化服务对象。

        当前阶段的设计思路：
        1. config 负责保存模型配置。
        2. client 负责真正和模型服务通信。
        3. 如果外部没有传进来，就在这里用默认方式创建。

        这样后面你既可以直接运行项目，
        也可以在测试里手动注入假的 client。
        """

        self.config = config or load_llm_config()
        self.client = client or create_llm_client(self.config)

    def chat(self, request: ChatRequest) -> ChatResponse:
        """处理一次聊天请求，并返回聊天响应。

        阶段 4 的建议拆法：
        1. 先整理 prompt 或消息输入。
        2. 再调用模型客户端。
        3. 最后把模型输出整理成 TutorReply。
        4. 再包装成 ChatResponse 返回。
        """

        user_id = request.user_id
        message = request.message

        # 一步一步处理信息 接收，调用，返回
        messages = self._build_messages(message)
        raw_reply = self._call_model(messages)
        reply = self._parse_model_reply(raw_reply)

        # 解析化回复，然后保存到表中
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
        """把消息发送给模型，并返回原始回复文本。

        TODO(阶段 4 - 占位任务 2):
        这里后面会调用 self.client.chat.completions.create(...)。
        """

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply

    def _parse_model_reply(self, raw_reply: str) -> TutorReply:
        """把模型原始回复解析成 TutorReply。
        """

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
