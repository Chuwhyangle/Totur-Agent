"""FastAPI application entry point."""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.attachments import router as attachments_router
from app.api.routes.chat import router as chat_router
from app.db import trace_db
from app.db.database import initialize_database
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.interview_jds import router as interview_jds_router
from app.api.routes.knowledge_documents import router as knowledge_documents_router
from app.api.routes.journal import router as journal_router
from app.api.routes.learning_progress import router as learning_progress_router
from app.api.routes.models import router as models_router
from app.api.routes.personas import router as personas_router
from app.api.routes.sessions import router as sessions_router
from app.clients.llm_client_pool import close_llm_clients
from app.clients.reranker_client import close_reranker_client
from app.clients.web_search_client import close_web_search_client
from app.config import ServerConfig
from app.mcp.settings import get_mcp_http_path, is_mcp_http_enabled
from app.services.workspaces.settings import is_workspaces_enabled
from app.services.documents.attachment_recovery_service import (
    get_attachment_recovery_service,
)
from app.services.agent.model_registry import validate_model_configuration
from app.services.knowledge_docs.recovery_service import recover_pending_documents

_server_config = ServerConfig.from_env()

allowed_origins = _server_config.ALLOWED_ORIGINS


logger = logging.getLogger(__name__)

ATTACHMENT_RECOVERY_SHUTDOWN_TIMEOUT_SECONDS = 2.0
ATTACHMENT_SWEEP_INTERVAL_SECONDS = 900.0


def _mark_recovery_done(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


async def _run_attachment_recovery(
    *,
    stop_requested: Callable[[], bool],
) -> None:
    """Run one bounded local recovery pass on a daemon worker thread."""

    loop = asyncio.get_running_loop()
    completed: asyncio.Future[None] = loop.create_future()

    def recover() -> None:
        try:
            service = get_attachment_recovery_service()
            service.recover_once(stop_requested=stop_requested)
        except Exception as exc:
            # Startup must remain available even if local recovery cannot initialize.
            logger.error(
                "attachment_startup_recovery_failed error_type=%s",
                type(exc).__name__,
            )
        finally:
            try:
                loop.call_soon_threadsafe(_mark_recovery_done, completed)
            except RuntimeError:
                # The bounded shutdown wait may finish before a blocked dependency.
                pass

    threading.Thread(
        target=recover,
        name="attachment-startup-recovery-worker",
        daemon=True,
    ).start()
    await completed


async def _run_attachment_sweep(
    *,
    stop_requested: Callable[[], bool],
    shutdown: asyncio.Event,
) -> None:
    """Repeat bounded recovery passes so expired attachments are reclaimed.

    TTL expiry only hides attachments from the accessible-attachment queries,
    so without a recurring pass their files and vectors accumulate forever.
    This is still a single-instance local sweep, not a distributed scheduler.
    """

    while not shutdown.is_set():
        with suppress(TimeoutError):
            await asyncio.wait_for(
                shutdown.wait(),
                timeout=ATTACHMENT_SWEEP_INTERVAL_SECONDS,
            )
        if shutdown.is_set():
            return
        # One pass logs and swallows its own failures, so the loop survives.
        await _run_attachment_recovery(stop_requested=stop_requested)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run bounded recovery and release shared clients on shutdown."""

    validate_model_configuration()
    # 业务库 schema 就绪先于观测库；只在启动时执行一次（A2）。
    initialize_database()
    try:
        recover_pending_documents()
    except Exception as exc:
        logger.error("knowledge_document_startup_recovery_failed error_type=%s", type(exc).__name__)
    if is_workspaces_enabled():
        try:
            from app.services.workspaces.asset_recovery_service import recover_workspace_assets_once

            recover_workspace_assets_once()
        except Exception as exc:
            logger.error("workspace_asset_startup_recovery_failed error_type=%s", type(exc).__name__)
    stop_event = threading.Event()
    shutdown_event = asyncio.Event()
    try:
        trace_db.start_writer()
    except Exception as exc:
        # Observability must never make the API unavailable.
        logger.warning("trace_writer_start_failed error_type=%s", type(exc).__name__)
    recovery_task = asyncio.create_task(
        _run_attachment_recovery(stop_requested=stop_event.is_set),
        name="attachment-startup-recovery",
    )
    sweep_task = asyncio.create_task(
        _run_attachment_sweep(
            stop_requested=stop_event.is_set,
            shutdown=shutdown_event,
        ),
        name="attachment-periodic-sweep",
    )
    try:
        if is_mcp_http_enabled():
            from app.mcp.server import get_mcp_http_lifespan

            async with get_mcp_http_lifespan():
                yield
        else:
            yield
    finally:
        stop_event.set()
        shutdown_event.set()
        try:
            await asyncio.wait_for(
                asyncio.shield(recovery_task),
                timeout=ATTACHMENT_RECOVERY_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "attachment_startup_recovery_shutdown_timeout timeout_seconds=%s",
                ATTACHMENT_RECOVERY_SHUTDOWN_TIMEOUT_SECONDS,
            )
            recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await recovery_task
        finally:
            # A pass in flight runs on a daemon thread, so cancelling the await
            # keeps shutdown bounded without joining a blocked dependency.
            sweep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweep_task
            try:
                trace_db.shutdown_writer()
            except Exception as exc:
                logger.warning(
                    "trace_writer_shutdown_failed error_type=%s",
                    type(exc).__name__,
                )
            close_reranker_client()
            close_web_search_client()
            close_llm_clients()


app = FastAPI(
    title="Tutor Agent API",
    version="0.1.0",
    lifespan=lifespan,
    root_path=_server_config.ROOT_PATH,
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
app.include_router(models_router)
# Session endpoints: create, list, and inspect chat history.
app.include_router(sessions_router)
# Interview JD endpoints: store user profiles before matching tools.
app.include_router(interview_jds_router)
app.include_router(knowledge_documents_router)
# Journal endpoints: daily learning diary entries.
app.include_router(journal_router)
# User-level learning progress endpoints, currently used by the SQL workspace.
app.include_router(learning_progress_router)

if is_workspaces_enabled():
    from app.api.routes.workspaces import router as workspaces_router
    from app.api.routes.workspace_assets import router as workspace_assets_router
    from app.api.routes.workspace_tasks import router as workspace_tasks_router
    from app.api.routes.workspace_artifacts import router as workspace_artifacts_router

    app.include_router(workspaces_router)
    app.include_router(workspace_assets_router)
    app.include_router(workspace_tasks_router)
    app.include_router(workspace_artifacts_router)

if is_mcp_http_enabled():
    from app.mcp.server import MCPMountPathMiddleware, get_mcp_http_app

    mcp_http_path = get_mcp_http_path()
    app.add_middleware(MCPMountPathMiddleware, mount_path=mcp_http_path)
    app.mount(mcp_http_path, get_mcp_http_app())
