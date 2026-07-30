"""Journal API 的请求和响应格式。"""

from pydantic import BaseModel, Field


class CreateJournalEntryRequest(BaseModel):
    """POST /api/journal/entries 的请求体。"""

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=50000)
    tags: str = Field(default="", max_length=500)
    entry_date: str | None = Field(default=None, description="日期 YYYY-MM-DD，默认今天")
    session_id: int | None = Field(default=None)
    persona_id: str = Field(default="journal")


class UpdateJournalEntryRequest(BaseModel):
    """PUT /api/journal/entries/{id} 的请求体。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=50000)
    tags: str | None = Field(default=None, max_length=500)
    entry_date: str | None = Field(default=None, description="日期 YYYY-MM-DD")


class JournalEntryItem(BaseModel):
    """API 返回的一条日记信息。"""

    id: int
    session_id: int | None
    persona_id: str
    title: str
    content: str
    tags: str
    entry_date: str
    created_at: str
    updated_at: str


class JournalEntryListResponse(BaseModel):
    """GET /api/journal/entries 的响应体。"""

    items: list[JournalEntryItem]
