"""pytest 全局 fixture。"""

import inspect

import pytest

from app.db import trace_db
from app.db.database import initialize_database
from app.db.engine import reset_engine_for_tests


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path, monkeypatch, request):
    """每个测试独立使用临时 SQLite 库，避免污染本地 tutor_agent.db。

    A2 后 schema 初始化唯一入口在 app lifespan；TestClient 直连不触发
    lifespan，由测试基建在此显式建 schema（业务路径仍只有 lifespan 一处）。
    测试函数体内直接调用 initialize_database 的（旧库迁移/建表验证），
    自己管理 schema 起点，测试基建不预建，避免与测试内建旧表冲突。
    """

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_engine_for_tests()
    try:
        source = inspect.getsource(request.node.function)
    except (OSError, TypeError):
        source = ""
    if "initialize_database" not in source:
        initialize_database()
    yield
    reset_engine_for_tests()


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
