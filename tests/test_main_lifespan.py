"""Shutdown regressions for the application lifespan."""

import asyncio
import threading
import time

import app.main as main_module


def test_lifespan_shutdown_is_bounded_when_recovery_dependency_hangs(
    monkeypatch,
    caplog,
):
    started = threading.Event()
    release = threading.Event()

    class BlockingRecoveryService:
        def recover_once(self, *, stop_requested):
            started.set()
            release.wait(timeout=5)

    monkeypatch.setattr(
        main_module,
        "get_attachment_recovery_service",
        lambda: BlockingRecoveryService(),
    )
    monkeypatch.setattr(main_module, "is_mcp_http_enabled", lambda: False)
    monkeypatch.setattr(main_module, "close_reranker_client", lambda: None)
    monkeypatch.setattr(main_module, "close_web_search_client", lambda: None)
    monkeypatch.setattr(
        main_module,
        "ATTACHMENT_RECOVERY_SHUTDOWN_TIMEOUT_SECONDS",
        0.05,
    )

    async def exercise_lifespan():
        try:
            before_shutdown = None
            async with main_module.lifespan(main_module.app):
                deadline = asyncio.get_running_loop().time() + 1
                while (
                    not started.is_set()
                    and asyncio.get_running_loop().time() < deadline
                ):
                    await asyncio.sleep(0.005)
                assert started.is_set()
                before_shutdown = time.monotonic()
            return time.monotonic() - before_shutdown
        finally:
            release.set()
            await asyncio.sleep(0)

    shutdown_elapsed = asyncio.run(exercise_lifespan())

    assert shutdown_elapsed < 0.5
    assert "attachment_startup_recovery_shutdown_timeout" in caplog.text
