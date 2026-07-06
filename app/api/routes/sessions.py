"""多会话 API 路由。"""

import json

from fastapi import APIRouter, HTTPException, Query, status

from app.db.models import ChatSessionRecord, ConversationRecord
from app.repositories.conversation_repository import list_recent_conversations
from app.repositories.session_repository import (
    create_session,
    get_session,
    list_sessions,
)
from app.schemas.chat import TutorReply
from app.schemas.conversations import ConversationItem
from app.schemas.sessions import (
    CreateSessionRequest,
    SessionConversationsResponse,
    SessionItem,
    SessionListResponse,
)
from app.services.agent.personas import (
    InvalidPersonaError,
    available_persona_ids,
    get_persona,
)


router = APIRouter(tags=["sessions"])


@router.post(
    "/sessions",
    response_model=SessionItem,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(request: CreateSessionRequest) -> SessionItem:
    """创建一个新的聊天会话。"""

    try:
        persona = get_persona(request.persona_id)
    except InvalidPersonaError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_persona_id",
                "persona_id": error.persona_id,
                "available_personas": available_persona_ids(),
            },
        ) from error

    # 当前阶段只创建会话，不会顺手创建聊天消息。
    session = create_session(
        user_id=request.user_id,
        title=request.title,
        persona_id=persona.persona_id,
    )

    return _session_item_from_record(session)


@router.get("/sessions", response_model=SessionListResponse)
def get_sessions(
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> SessionListResponse:
    """查询某个用户最近的会话列表。"""

    sessions = list_sessions(user_id=user_id, limit=limit)

    return SessionListResponse(
        user_id=user_id,
        items=[_session_item_from_record(session) for session in sessions],
    )


@router.get(
    "/sessions/{session_id}/conversations",
    response_model=SessionConversationsResponse,
)
def get_session_conversations(
    session_id: int,
    limit: int = Query(default=20, ge=1, le=100),
) -> SessionConversationsResponse:
    """查询某个会话里的最近对话记录。"""

    # 先查会话本身，确认 session_id 存在，同时拿到它属于哪个 user_id。
    session = get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    records = list_recent_conversations(
        user_id=session.user_id,
        session_id=session.id,
        limit=limit,
    )

    return SessionConversationsResponse(
        session_id=session.id,
        user_id=session.user_id,
        title=session.title,
        persona_id=session.persona_id,
        items=[_conversation_item_from_record(record) for record in records],
    )


def _session_item_from_record(record: ChatSessionRecord) -> SessionItem:
    """把数据库里的会话记录转换成 API 响应对象。"""

    return SessionItem(
        id=record.id,
        user_id=record.user_id,
        title=record.title,
        persona_id=record.persona_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _conversation_item_from_record(record: ConversationRecord) -> ConversationItem:
    """把数据库里的对话记录转换成历史消息响应对象。"""

    reply_data = json.loads(record.reply_json)
    reply = TutorReply.model_validate(reply_data)

    return ConversationItem(
        id=record.id,
        message=record.message,
        reply=reply,
        created_at=record.created_at,
    )
