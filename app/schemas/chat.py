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


class ToolCallTrace(BaseModel):
    """一次工具调用的调试摘要。"""

    name: str
    arguments: dict
    ok: bool
    returned_count: int | None = None
    top_titles: list[str] = Field(default_factory=list)
    error: str | None = None


class ToolTrace(BaseModel):
    """一次 /chat 请求里的工具调用调试信息。"""

    used: bool
    calls: list[ToolCallTrace] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""

    user_id: str
    session_id: int
    message: str
    reply: TutorReply
    tool_trace: ToolTrace
