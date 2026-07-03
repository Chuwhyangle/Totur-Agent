"""聊天接口路由文件。

这个文件负责：
1. 定义聊天相关接口，例如 POST /chat。
2. 接收前端传来的 ChatRequest。
3. 把请求交给 TutorAgentService 处理。
4. 返回符合 ChatResponse 格式的数据。

这个文件不负责：
1. 创建 FastAPI 主应用。
2. 读取 .env。
3. 直接调用大模型 SDK。

当前阶段目标：
让路由只做“收请求、交给 service、回结果”这三件事。
"""

from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.tutor_agent_service import TutorAgentService

# 子路由容器
router = APIRouter(tags=["chat"])

# 先准备好服务对象。
tutor_agent_service = TutorAgentService()

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """聊天接口入口。

    路由层的职责很轻：
    1. 接收请求体。
    2. 调用 service。
    3. 把 service 的结果返回给前端。
    """

    return tutor_agent_service.chat(request)
