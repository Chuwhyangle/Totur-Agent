"""学习进度 API 的请求和响应格式。"""

from pydantic import BaseModel, Field

from app.db.models import LearningProgressSource, LearningProgressStatus
from app.services.learning_progress_service import (
    MAX_EVIDENCE_LENGTH,
    MAX_NEXT_STEP_LENGTH,
    MAX_SUBJECT_LENGTH,
    MAX_TOPIC_LENGTH,
    MAX_USER_ID_LENGTH,
)


class UpsertLearningProgressRequest(BaseModel):
    """PUT /learning-progress 的请求体。"""

    user_id: str = Field(..., min_length=1, max_length=MAX_USER_ID_LENGTH)
    subject: str = Field(default="sql", min_length=1, max_length=MAX_SUBJECT_LENGTH)
    topic: str = Field(..., min_length=1, max_length=MAX_TOPIC_LENGTH)
    level: int = Field(default=0, ge=0, le=3)
    status: LearningProgressStatus = LearningProgressStatus.LEARNING
    evidence: str | None = Field(default=None, max_length=MAX_EVIDENCE_LENGTH)
    next_step: str | None = Field(default=None, max_length=MAX_NEXT_STEP_LENGTH)


class LearningProgressItem(BaseModel):
    """一条公开的学习进度记录。"""

    id: int
    user_id: str
    subject: str
    topic: str
    level: int
    status: LearningProgressStatus
    evidence: str | None
    next_step: str | None
    source: LearningProgressSource
    updated_at: str


class LearningProgressListResponse(BaseModel):
    """GET /learning-progress 的响应体。"""

    user_id: str
    subject: str
    items: list[LearningProgressItem]
