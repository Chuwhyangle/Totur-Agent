"""Prompt persona API routes."""

from fastapi import APIRouter

from app.schemas.personas import PersonaResponse
from app.services.agent.personas import list_personas


router = APIRouter(tags=["personas"])


@router.get("/personas", response_model=list[PersonaResponse])
def personas() -> list[PersonaResponse]:
    """返回当前可用的人设列表。"""

    return [
        PersonaResponse(
            persona_id=persona.persona_id,
            name=persona.name,
            description=persona.description,
        )
        for persona in list_personas()
    ]
