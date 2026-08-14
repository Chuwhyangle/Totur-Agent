"""Opt-in integration coverage for a dedicated MySQL trace database."""

import os

import pytest

from app.config import TraceDbConfig
from app.db import trace_db
from app.db.trace_schema import initialize_trace_schema


@pytest.mark.mysql
def test_mysql_schema_is_idempotent_and_trace_events_share_id(monkeypatch):
    if os.getenv("TRACE_DB_TEST_ENABLED", "").strip().lower() != "true":
        pytest.skip("set TRACE_DB_TEST_ENABLED=true to run against a dedicated test database")

    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL is not installed")

    required = {
        "host": os.getenv("TRACE_DB_TEST_HOST", "127.0.0.1"),
        "port": int(os.getenv("TRACE_DB_TEST_PORT", "3306")),
        "user": os.getenv("TRACE_DB_TEST_USER", ""),
        "password": os.getenv("TRACE_DB_TEST_PASSWORD", ""),
        "name": os.getenv("TRACE_DB_TEST_NAME", ""),
    }
    if not required["user"] or not required["password"] or not required["name"]:
        pytest.skip(
            "TRACE_DB_TEST_USER, TRACE_DB_TEST_PASSWORD and TRACE_DB_TEST_NAME are required"
        )

    config = TraceDbConfig(
        enabled=True,
        host=required["host"],
        port=required["port"],
        user=required["user"],
        password=required["password"],
        name=required["name"],
        connect_timeout_seconds=2,
        queue_size=100,
        shutdown_flush_seconds=5,
        capture_content=False,
    )
    trace_db.reset_for_tests()
    monkeypatch.setattr(trace_db, "_TRACE_CONFIG", config)

    try:
        connection = pymysql.connect(**config.connection_kwargs)
        try:
            initialize_trace_schema(connection)
        finally:
            connection.close()
        connection = pymysql.connect(**config.connection_kwargs)
        try:
            initialize_trace_schema(connection)
        finally:
            connection.close()

        trace_db.start_writer(config)
        trace_id = trace_db.start_trace(
            user_id="mysql-test-user",
            persona_id="tutor",
            model="mysql-test-model",
            question="integration question",
        )
        trace_db.save_retrieval_event(
            trace_id=trace_id,
            query="integration query",
            collection="test",
        )
        trace_db.save_llm_call(
            trace_id=trace_id,
            round_number=1,
            call_type="final",
            model="mysql-test-model",
        )
        trace_db.save_tool_call(
            trace_id=trace_id,
            round_number=1,
            tool_name="mysql_test_tool",
            ok=1,
            args_preview={"ok": True},
        )
        trace_db.finish_trace(
            trace_id=trace_id,
            user_id="mysql-test-user",
            persona_id="tutor",
            model="mysql-test-model",
            total_ms=10,
            status="OK",
            llm_calls=1,
            tool_calls=1,
        )
        assert trace_db.flush(5) is True

        connection = pymysql.connect(**config.connection_kwargs)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, llm_calls, tool_calls FROM agent_traces WHERE trace_id=%s",
                    (trace_id,),
                )
                root = cursor.fetchone()
                counts = {}
                for table_name in (
                    "retrieval_events",
                    "llm_calls",
                    "tool_calls",
                ):
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table_name} WHERE trace_id=%s",
                        (trace_id,),
                    )
                    counts[table_name] = cursor.fetchone()[0]
        finally:
            connection.close()

        assert root == ("OK", 1, 1)
        assert counts == {
            "retrieval_events": 1,
            "llm_calls": 1,
            "tool_calls": 1,
        }
    finally:
        trace_db.shutdown_writer(timeout=5)
