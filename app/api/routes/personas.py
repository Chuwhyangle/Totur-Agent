"""Prompt persona API routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.personas import CustomPersonaRequest, PersonaResponse
from app.services.agent.persona_service import CustomPersonaError, PersonaService


router = APIRouter(tags=["personas"])
persona_service = PersonaService()


@router.get("/personas", response_model=list[PersonaResponse], response_model_exclude_none=True)
def personas(user_id: str | None = Query(default=None, min_length=1)) -> list[PersonaResponse]:
    """返回当前可用的人设列表。"""

    return [
        PersonaResponse(
            persona_id=persona.persona_id,
            name=persona.name,
            description=persona.description,
            system_prompt=persona.system_prompt if persona.persona_id not in {"tutor", "algorithm_coach", "interviewer", "journal"} else None,
        )
        for persona in persona_service.list_for_user(user_id)
    ]


@router.post("/personas/custom", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
def create_custom_persona(request: CustomPersonaRequest) -> PersonaResponse:
    try:
        record = persona_service.create(**request.model_dump())
    except CustomPersonaError as error:
        raise HTTPException(status_code=422, detail={"error": "invalid_persona", "message": str(error)}) from error
    return PersonaResponse(persona_id=record.id, name=record.name, description=record.description, system_prompt=record.system_prompt)


@router.post("/personas", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
def create_persona(request: CustomPersonaRequest) -> PersonaResponse:
    """Compatibility alias for creating a custom persona."""

    return create_custom_persona(request)


@router.patch("/personas/custom/{persona_id}", response_model=PersonaResponse)
def update_custom_persona(persona_id: str, request: CustomPersonaRequest) -> PersonaResponse:
    try:
        record = persona_service.update(persona_id=persona_id, **request.model_dump())
    except CustomPersonaError as error:
        raise HTTPException(status_code=404, detail="Persona not found") from error
    return PersonaResponse(persona_id=record.id, name=record.name, description=record.description, system_prompt=record.system_prompt)


@router.put("/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(persona_id: str, request: CustomPersonaRequest) -> PersonaResponse:
    return update_custom_persona(persona_id, request)


@router.delete("/personas/custom/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_custom_persona(persona_id: str, user_id: str = Query(..., min_length=1)) -> None:
    try:
        persona_service.disable(user_id=user_id, persona_id=persona_id)
    except CustomPersonaError as error:
        raise HTTPException(status_code=404, detail="Persona not found") from error


@router.delete("/personas/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_persona(persona_id: str, user_id: str = Query(..., min_length=1)) -> None:
    return disable_custom_persona(persona_id, user_id)
