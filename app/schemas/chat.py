"""Chat API 的请求和响应格式。"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /chat 的请求体。"""

    user_id: str = Field(..., min_length=1)
    session_id: int | None = None
    message: str = Field(..., min_length=1)


class TutorReply(BaseModel):
    """模型返回的结构化导师回复。"""

    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]


class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""

    user_id: str
    session_id: int
    message: str
    reply: TutorReply
