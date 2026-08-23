"""对话历史查询接口。"""

from fastapi import APIRouter, Query

from app.repositories.conversation_repository import list_recent_conversations
from app.schemas.conversations import ConversationItem, ConversationListResponse
from app.services.agent.response_parser import ResponseParser


router = APIRouter(tags=["conversations"])


@router.get("/conversations/{user_id}", response_model=ConversationListResponse)
def get_conversations(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    """查询某个用户最近的对话历史。"""

    records = list_recent_conversations(user_id=user_id, limit=limit)
    parser = ResponseParser()
    items: list[ConversationItem] = []

    for record in records:
        reply = parser.parse_stored_reply(record.reply_json, record.reply_format)

        items.append(
            ConversationItem(
                id=record.id,
                message=record.message,
                reply=reply,
                created_at=record.created_at,
            )
        )

    return ConversationListResponse(
        user_id=user_id,
        items=items,
    )
