"""FastAPI 后端应用入口。

这个文件负责：
1. 创建整个后端应用对象 app = FastAPI(...)。
2. 注册各个路由模块，比如 chat_router、health_router。
3. 放全局配置，例如项目名称、版本号、中间件等。

这个文件不适合写太多具体业务逻辑。
例如：
- 聊天接口逻辑应该放到 app/api/routes/chat.py。
- 健康检查接口应该放到 app/api/routes/health.py。
- 请求体和响应体格式应该放到 app/schemas/。
- 复杂业务处理后续应该放到 app/services/。

阶段 3 之后的结构目标：
app/main.py 只装配应用；
app/api/routes/ 只管理接口；
app/services/ 处理业务逻辑。
"""

from fastapi import FastAPI
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router

# FastAPI 是后端应用对象。
# 你可以把 app 理解为整个 API 服务的入口。
# 后续阶段会把路由拆到 app/api/routes/ 目录里。

app = FastAPI(
    title="Tutor Agent API",
    version="0.1.0",
)

# 把各个“路由模块”注册到主应用里。
# 你可以把 include_router(...) 理解为：
# “把这个接口文件挂到整个网站里，让外部可以访问到它”。
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(health_router)

# TODO(阶段 3): TutorAgentService 框架已创建。
# 下一步：把 /chat 里的固定回复逻辑迁移到 app/services/tutor_agent_service.py。
