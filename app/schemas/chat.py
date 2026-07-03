"""聊天接口的数据格式定义。

这个文件负责：
1. 定义 POST /chat 的请求体 ChatRequest。
2. 定义学习导师回复 TutorReply。
3. 定义 POST /chat 的响应体 ChatResponse。

新手理解：
这里的类不是普通业务类，而是 Pydantic 模型。
FastAPI 会根据这些类自动做 JSON 校验和文档生成。

这个文件不负责：
1. 写接口路径。
2. 调用大模型。
3. 查询数据库。
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /chat 的请求体。

    BaseModel 来自 Pydantic。
    FastAPI 会用它自动校验前端传进来的 JSON。
    """
    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class TutorReply(BaseModel):
    """学习导师的结构化回复。

    阶段 2 先返回固定内容。
    阶段 4 会把它升级成真实模型的结构化输出。
    """

    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]


class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""

    user_id: str
    message: str
    reply: TutorReply
