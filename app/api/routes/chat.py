"""聊天 API 路由。"""

from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent.personas import (
    InvalidPersonaError,
    available_persona_ids,
)
from app.services.tutor_agent_service import (
    ChatSessionNotFoundError,
    TutorAgentService,
)

router = APIRouter(tags=["chat"])

tutor_agent_service = TutorAgentService()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """处理一次导师聊天请求。"""

    try:
        return tutor_agent_service.chat(request)
    except InvalidPersonaError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_persona_id",
                "persona_id": error.persona_id,
                "available_personas": available_persona_ids(),
            },
        ) from error
    except ChatSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from error
