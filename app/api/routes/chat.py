"""Chat API routes."""

from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.tutor_agent_service import TutorAgentService

router = APIRouter(tags=["chat"])

tutor_agent_service = TutorAgentService()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Handle one tutor chat request."""

    return tutor_agent_service.chat(request)
