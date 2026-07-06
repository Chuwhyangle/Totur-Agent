"""多会话 API 的请求和响应格式。"""

from pydantic import BaseModel, Field

from app.schemas.conversations import ConversationItem


class CreateSessionRequest(BaseModel):
    """POST /sessions 的请求体。"""

    user_id: str = Field(..., min_length=1)
    title: str | None = Field(default=None, max_length=100)
    persona_id: str = "tutor"


class SessionItem(BaseModel):
    """API 返回的一条会话信息。"""

    id: int
    user_id: str
    title: str
    persona_id: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """GET /sessions 的响应体。"""

    user_id: str
    items: list[SessionItem]


class SessionConversationsResponse(BaseModel):
    """GET /sessions/{session_id}/conversations 的响应体。"""

    session_id: int
    user_id: str
    title: str
    persona_id: str
    items: list[ConversationItem]
