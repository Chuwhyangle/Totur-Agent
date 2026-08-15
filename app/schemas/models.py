"""Public model catalog API schemas."""

from pydantic import BaseModel


class ModelResponse(BaseModel):
    """Safe model metadata returned by GET /models."""

    model_id: str
    display_name: str
    description: str
    supports_thinking: bool
    is_default: bool
