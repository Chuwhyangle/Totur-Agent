"""对话历史查询接口。"""

import json

from fastapi import APIRouter, Query

from app.repositories.conversation_repository import list_recent_conversations
from app.schemas.chat import TutorReply
from app.schemas.conversations import ConversationItem, ConversationListResponse


router = APIRouter(tags=["conversations"])


@router.get("/conversations/{user_id}", response_model=ConversationListResponse)
def get_conversations(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    """查询某个用户最近的对话历史。"""

    records = list_recent_conversations(user_id=user_id, limit=limit)
    items: list[ConversationItem] = []

    for record in records:
        reply_data = json.loads(record.reply_json)
        reply = TutorReply.model_validate(reply_data)

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
