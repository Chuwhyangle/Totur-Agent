"""对话历史接口的数据格式定义。"""

from pydantic import BaseModel

from app.schemas.chat import TutorReply


class ConversationItem(BaseModel):
    """GET /conversations/{user_id} 返回列表中的一条历史记录。"""

    id: int
    message: str
    reply: TutorReply
    created_at: str


class ConversationListResponse(BaseModel):
    """GET /conversations/{user_id} 的响应体。"""

    user_id: str
    items: list[ConversationItem]
