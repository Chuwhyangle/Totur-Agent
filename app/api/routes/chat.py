"""聊天 API 路由。"""

from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import ChatRequest, ChatResponse
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
    except ChatSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from error
