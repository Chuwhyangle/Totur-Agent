"""pytest 全局 fixture。"""

import pytest

from app.db import trace_db


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
