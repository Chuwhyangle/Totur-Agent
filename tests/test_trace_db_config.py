"""Tests for trace database configuration loading and test isolation."""

import pytest

from app.db import trace_db


_ORIGINAL_LOAD_DB_CONFIG = trace_db.load_db_config


def _use_original_loader(monkeypatch):
    monkeypatch.setattr(trace_db, "load_db_config", _ORIGINAL_LOAD_DB_CONFIG)
    monkeypatch.setattr(trace_db, "_DB_CONFIG", None)


def test_load_db_config_caches_dotenv_result_and_returns_copy(monkeypatch):
    _use_original_loader(monkeypatch)
    dotenv_calls = []
    monkeypatch.setattr(
        trace_db,
        "load_dotenv",
        lambda: dotenv_calls.append(True),
    )
    monkeypatch.setenv("TRACE_DB_HOST", "db.example")
    monkeypatch.setenv("TRACE_DB_PORT", "3307")
    monkeypatch.setenv("TRACE_DB_USER", "trace-user")
    monkeypatch.setenv("TRACE_DB_PASSWORD", "trace-password")
    monkeypatch.setenv("TRACE_DB_NAME", "trace-db")

    first = trace_db.load_db_config()
    first["user"] = "mutated"
    second = trace_db.load_db_config()

    assert dotenv_calls == [True]
    assert second["user"] == "trace-user"
    assert first is not second


def test_load_db_config_still_rejects_missing_required_values(monkeypatch):
    _use_original_loader(monkeypatch)
    monkeypatch.setattr(trace_db, "load_dotenv", lambda: None)
    for key in (
        "TRACE_DB_USER",
        "TRACE_DB_PASSWORD",
        "TRACE_DB_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match=r"缺少 TRACE_DB_\* 配置"):
        trace_db.load_db_config()


def test_autouse_fixture_blocks_real_db_loader():
    with pytest.raises(RuntimeError, match="测试期间禁止连接真实 MySQL"):
        trace_db.load_db_config()
