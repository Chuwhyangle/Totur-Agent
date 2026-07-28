"""聊天 API 路由。"""

import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent.personas import (
    InvalidPersonaError,
    available_persona_ids,
)
from app.services.documents.attachment_retrieval_service import (
    AttachmentIndexMissingError,
    AttachmentNoRelevantEvidenceError,
    AttachmentNotFoundError,
    AttachmentNotReadyError,
    AttachmentProcessingFailedError,
    AttachmentRetrievalFailedError,
)
from app.services.tutor_agent_service import (
    ChatSessionNotFoundError,
    SessionPersonaMismatchError,
    TutorAgentService,
)

router = APIRouter(tags=["chat"])

tutor_agent_service = TutorAgentService()


def _format_sse_event(event_type: str, data: dict) -> str:
    """Format a dict as an SSE event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Handle a chat request with SSE streaming.

    Returns a text/event-stream response with events:
        - token: partial reply text
        - tool_call: tool invocation started
        - tool_result: tool invocation completed
        - done: full response with sources
        - error: error message
    """

    def event_generator():
        terminal_event_sent = False
        try:
            for event in tutor_agent_service.chat_stream(request):
                event_type = event.get("event", "token")
                data = event.get("data", {})
                yield _format_sse_event(event_type, data)
                if event_type in {"done", "error"}:
                    terminal_event_sent = True
                    break
            if not terminal_event_sent:
                yield _format_sse_event(
                    "error",
                    {"message": "Stream ended before completion"},
                )
        except Exception as exc:
            yield _format_sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


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
    except SessionPersonaMismatchError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "session_persona_mismatch",
                "session_id": error.session_id,
                "session_persona_id": error.session_persona_id,
                "request_persona_id": error.request_persona_id,
            },
        ) from error
    except AttachmentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "attachment_not_found"},
        ) from error
    except AttachmentNotReadyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "attachment_not_ready"},
        ) from error
    except AttachmentProcessingFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "attachment_processing_failed"},
        ) from error
    except AttachmentIndexMissingError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "attachment_index_missing"},
        ) from error
    except AttachmentNoRelevantEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "attachment_no_relevant_evidence"},
        ) from error
    except AttachmentRetrievalFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "attachment_retrieval_failed"},
        ) from error
    except ChatSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from error
