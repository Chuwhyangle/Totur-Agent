"""Available chat model API routes."""

from fastapi import APIRouter

from app.schemas.models import ModelResponse
from app.services.agent.model_registry import available_models, default_model_id


router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelResponse])
def models() -> list[ModelResponse]:
    """Return public metadata for models usable by the current deployment."""

    default_id = default_model_id()
    return [
        ModelResponse(
            model_id=spec.model_id,
            display_name=spec.display_name,
            description=spec.description,
            supports_thinking=spec.supports_thinking,
            is_default=spec.model_id == default_id,
        )
        for spec in available_models().values()
    ]
