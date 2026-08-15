"""pytest 全局 fixture。"""

import pytest

from app.db import trace_db


@pytest.fixture(autouse=True)
def configure_test_chat_models(monkeypatch):
    """Keep application lifespan tests independent from developer .env files."""

    monkeypatch.setenv(
        "ENABLED_MODELS",
        "ds-flash-fast,ds-flash-think,ds-pro-deep",
    )
    monkeypatch.setenv("DEFAULT_MODEL_ID", "ds-flash-fast")
    monkeypatch.setenv("DEEPSEEK_KEY", "test-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")


@pytest.fixture(autouse=True)
def skip_trace_writes(monkeypatch):
    """Disable real trace writes while keeping one facade patch point."""

    monkeypatch.setenv("TRACE_DB_ENABLED", "false")
    trace_db.reset_for_tests()

    def _forbid_real_db():
        raise RuntimeError("测试期间禁止连接真实 MySQL")

    monkeypatch.setattr(
        "app.db.trace_db.load_db_config",
        _forbid_real_db,
    )
