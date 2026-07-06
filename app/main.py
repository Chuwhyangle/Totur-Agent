"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.interview_jds import router as interview_jds_router
from app.api.routes.personas import router as personas_router
from app.api.routes.sessions import router as sessions_router

allowed_origins = [
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
]

app = FastAPI(
    title="Tutor Agent API",
    version="0.1.0",
)

# 允许本地 Vite 前端从浏览器访问后端 API。
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(health_router)
app.include_router(personas_router)
# 注册多会话接口：创建会话、列出会话、读取某个会话的历史。
app.include_router(sessions_router)
# 注册目标岗位 JD 接口：先存储用户资料，后续再接面试工具检索。
app.include_router(interview_jds_router)
