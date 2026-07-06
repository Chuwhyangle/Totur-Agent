"""Prompt persona API schemas."""

from pydantic import BaseModel


class PersonaResponse(BaseModel):
    """GET /personas 返回的人设摘要，不包含 system prompt。"""

    persona_id: str
    name: str
    description: str
