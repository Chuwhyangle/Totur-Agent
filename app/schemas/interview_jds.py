"""Interview JD API 的请求和响应格式。"""

from pydantic import BaseModel, Field


class CreateInterviewJDRequest(BaseModel):
    """POST /interview-jds 的请求体。"""

    user_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=120)
    role_family: str | None = Field(default=None, max_length=80)
    seniority: str | None = Field(default=None, max_length=80)
    target_graduation_years: list[str] = Field(default_factory=list)
    raw_text: str = Field(..., min_length=1)
    responsibilities: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    bonus_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)


class InterviewJDItem(BaseModel):
    """API 返回的一条 JD 信息。"""

    id: int
    user_id: str
    title: str
    role_family: str | None
    seniority: str | None
    target_graduation_years: list[str]
    raw_text: str
    responsibilities: list[str]
    must_have: list[str]
    core_skills: list[str]
    preferred_skills: list[str]
    bonus_skills: list[str]
    keywords: list[str]
    interview_focus: list[str]
    created_at: str
    updated_at: str


class InterviewJDListResponse(BaseModel):
    """GET /interview-jds 的响应体。"""

    user_id: str
    items: list[InterviewJDItem]
