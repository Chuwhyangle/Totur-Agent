"""Chat API request and response schemas."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /chat request body."""

    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class TutorReply(BaseModel):
    """Structured tutor reply returned by the model."""

    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]


class ChatResponse(BaseModel):
    """POST /chat response body."""

    user_id: str
    message: str
    reply: TutorReply
