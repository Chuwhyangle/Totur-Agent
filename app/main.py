"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.attachments import router as attachments_router
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.interview_jds import router as interview_jds_router
from app.api.routes.personas import router as personas_router
from app.api.routes.sessions import router as sessions_router
from app.clients.reranker_client import close_reranker_client
from app.clients.web_search_client import close_web_search_client
from app.mcp.settings import get_mcp_http_path, is_mcp_http_enabled
from app.services.documents.attachment_recovery_service import (
    get_attachment_recovery_service,
)

allowed_origins = [
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
]


logger = logging.getLogger(__name__)


async def _run_attachment_recovery() -> None:
    """Run one bounded local recovery pass without blocking startup."""

    try:
        service = get_attachment_recovery_service()
        await asyncio.to_thread(service.recover_once)
    except Exception as exc:
        # Startup must remain available even if local recovery cannot initialize.
        logger.error(
            "attachment_startup_recovery_failed error_type=%s",
            type(exc).__name__,
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run bounded recovery and release shared clients on shutdown."""

    recovery_task = asyncio.create_task(
        _run_attachment_recovery(),
        name="attachment-startup-recovery",
    )
    try:
        if is_mcp_http_enabled():
            from app.mcp.server import get_mcp_http_lifespan

            async with get_mcp_http_lifespan():
                yield
        else:
            yield
    finally:
        # The pass is bounded; awaiting it prevents an unobserved task exception.
        await recovery_task
        close_reranker_client()
        close_web_search_client()


app = FastAPI(
    title="Tutor Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow local Vite frontends to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(attachments_router)
app.include_router(conversations_router)
app.include_router(health_router)
app.include_router(personas_router)
# Session endpoints: create, list, and inspect chat history.
app.include_router(sessions_router)
# Interview JD endpoints: store user profiles before matching tools.
app.include_router(interview_jds_router)

if is_mcp_http_enabled():
    from app.mcp.server import MCPMountPathMiddleware, get_mcp_http_app

    mcp_http_path = get_mcp_http_path()
    app.add_middleware(MCPMountPathMiddleware, mount_path=mcp_http_path)
    app.mount(mcp_http_path, get_mcp_http_app())
