"""Chat API 的请求和响应格式。"""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /chat 的请求体。"""

    user_id: str = Field(..., min_length=1)
    session_id: int | None = None
    message: str = Field(..., min_length=1)
    persona_id: str | None = None


class Source(BaseModel):
    """Public source copied from the server-side evidence ledger."""

    id: str
    title: str
    url: str
    domain: str


class TutorReply(BaseModel):
    """模型返回的结构化导师回复。"""

    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]
    sources: list[Source] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list, exclude=True)


class ToolResultPreview(BaseModel):
    """工具结果的轻量调试预览，不包含数据库 id 或完整原文。"""

    title: str
    match_score: int | None = None
    matched_fields: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)
    raw_text_excerpt: str = ""


class ToolCallTrace(BaseModel):
    """一次工具调用的调试摘要。"""

    round: int
    name: str
    arguments: dict
    ok: bool
    returned_count: int | None = None
    top_titles: list[str] = Field(default_factory=list)
    result_preview: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class ToolTrace(BaseModel):
    """一次 /chat 请求里的工具调用调试信息。"""

    used: bool
    calls: list[ToolCallTrace] = Field(default_factory=list)
    ledger: dict[str, Source] = Field(default_factory=dict, exclude=True)


class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""

    user_id: str
    session_id: int
    message: str
    reply: TutorReply
    tool_trace: ToolTrace
