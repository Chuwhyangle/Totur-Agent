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


def test_lifespan_periodic_sweep_repeats_recovery_until_shutdown(monkeypatch):
    """Expired attachments need recurring passes, not just the startup one."""

    calls: list[int] = []

    class CountingRecoveryService:
        def recover_once(self, *, stop_requested):
            calls.append(len(calls) + 1)

    monkeypatch.setattr(
        main_module,
        "get_attachment_recovery_service",
        lambda: CountingRecoveryService(),
    )
    monkeypatch.setattr(main_module, "is_mcp_http_enabled", lambda: False)
    monkeypatch.setattr(main_module, "close_reranker_client", lambda: None)
    monkeypatch.setattr(main_module, "close_web_search_client", lambda: None)
    monkeypatch.setattr(main_module, "ATTACHMENT_SWEEP_INTERVAL_SECONDS", 0.01)

    async def exercise_lifespan():
        async with main_module.lifespan(main_module.app):
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 2
            while len(calls) < 3 and loop.time() < deadline:
                await asyncio.sleep(0.01)
            assert len(calls) >= 3, "periodic sweep did not repeat"
        at_shutdown = len(calls)
        # Ten sweep intervals: a live loop would add far more than one pass.
        await asyncio.sleep(0.1)
        return at_shutdown, len(calls)

    at_shutdown, final = asyncio.run(exercise_lifespan())

    assert final - at_shutdown <= 1
