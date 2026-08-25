"""Prompt persona API schemas."""

from pydantic import BaseModel, Field


class PersonaResponse(BaseModel):
    """GET /personas 返回的人设摘要，不包含 system prompt。"""

    persona_id: str
    name: str
    description: str
    system_prompt: str | None = None


class CustomPersonaRequest(BaseModel):
    """Create or update a user-owned persona."""

    user_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    system_prompt: str = Field(..., min_length=1, max_length=12000)
