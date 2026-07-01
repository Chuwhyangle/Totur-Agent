from pydantic import BaseModel, Field
from fastapi import FastAPI


# FastAPI 是后端应用对象。
# 你可以把 app 理解为整个 API 服务的入口。
# 后续阶段会把路由拆到 app/api/routes/ 目录里。
app = FastAPI(
    title="Tutor Agent API",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    """POST /chat 的请求体。

    BaseModel 来自 Pydantic。
    FastAPI 会用它自动校验前端传进来的 JSON。
    """

    # user_id 是轻量多用户雏形，第一版先不做登录。
    user_id: str = Field(..., min_length=1)
    # message 是用户发给学习辅导 Agent 的问题。
    message: str = Field(..., min_length=1)


class TutorReply(BaseModel):
    """学习导师的结构化回复。

    阶段 2 先返回固定内容。
    阶段 4 会把它升级成真实模型的结构化输出。
    """

    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]


class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""

    user_id: str
    message: str
    reply: TutorReply


@app.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口。

    用途：
    1. 确认 FastAPI 服务已经启动。
    2. 给你练习第一个 GET 接口。
    3. 后续部署时也可以用它判断服务是否活着。
    """

    return {
        "status": "ok",
        "service": "tutor-agent-api",
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """学习对话接口的阶段 2 占位版本。

    当前阶段只练习：
    1. 接收 JSON 请求体。
    2. 读取 user_id 和 message。
    3. 返回结构化 JSON 响应。

    这里暂时不调用真实模型。
    阶段 3 会把业务逻辑拆到 service。
    阶段 4 会接入结构化导师回复。
    """

    return ChatResponse(
        user_id=request.user_id,
        message=request.message,
        reply=TutorReply(
            answer="这是阶段 2 的固定占位回复。",
            next_task="下一步会把这里接入阶段 1 的模型调用逻辑。",
            exercise="请用 Swagger 的 /docs 页面调用一次 POST /chat。",
            checkpoints=[
                "你能解释什么是 POST 请求",
                "你能说明请求体和响应体的区别",
                "你能在 /docs 页面测试接口",
            ],
        ),
    )


# TODO(阶段 2): 手动启动服务并访问 http://127.0.0.1:8000/docs。
# TODO(阶段 2): 用 Swagger 页面测试 GET /health 和 POST /chat。
# TODO(阶段 3): 把路由从 main.py 拆分到 app/api/routes/。
# TODO(阶段 3): 把 ChatRequest、TutorReply、ChatResponse 拆分到 app/schemas/。
# TODO(阶段 3): 新增 TutorAgentService，让 /chat 不直接写业务逻辑。
