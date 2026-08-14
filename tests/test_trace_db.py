"""Tests for the trace facade and its non-blocking writer."""

import json
import time

from app.config import TraceDbConfig
from app.db import trace_db


TRACE_ID = "a" * 32


class RecordingWriter:
    def __init__(self):
        self.tasks = []

    def enqueue(self, sql, params):
        self.tasks.append((sql, params))
        return True


def enabled_config(*, capture_content=False, queue_size=10):
    return TraceDbConfig(
        enabled=True,
        host="127.0.0.1",
        port=3306,
        user="trace_user",
        password="not-logged",
        name="trace_test",
        queue_size=queue_size,
        capture_content=capture_content,
        shutdown_flush_seconds=0.2,
    )


def test_trace_config_reads_operational_settings_lazily(monkeypatch):
    monkeypatch.setenv("TRACE_DB_ENABLED", "true")
    monkeypatch.setenv("TRACE_DB_HOST", "trace-db")
    monkeypatch.setenv("TRACE_DB_PORT", "3310")
    monkeypatch.setenv("TRACE_DB_USER", "trace-user")
    monkeypatch.setenv("TRACE_DB_PASSWORD", "trace-password")
    monkeypatch.setenv("TRACE_DB_NAME", "trace-test")
    monkeypatch.setenv("TRACE_DB_CONNECT_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("TRACE_DB_QUEUE_SIZE", "17")
    monkeypatch.setenv("TRACE_DB_SHUTDOWN_FLUSH_SECONDS", "3")
    monkeypatch.setenv("TRACE_DB_CAPTURE_CONTENT", "true")

    config = TraceDbConfig.from_env()

    assert config.enabled is True
    assert config.host == "trace-db"
    assert config.port == 3310
    assert config.queue_size == 17
    assert config.shutdown_flush_seconds == 3
    assert config.capture_content is True


def use_recording_writer(monkeypatch, *, capture_content=False):
    writer = RecordingWriter()
    monkeypatch.setattr(
        trace_db,
        "_TRACE_CONFIG",
        enabled_config(capture_content=capture_content),
    )
    monkeypatch.setattr(trace_db, "_TRACE_WRITER", writer)
    monkeypatch.setattr(trace_db, "start_writer", lambda config=None: None)
    return writer


def test_disabled_trace_api_is_a_noop(monkeypatch):
    monkeypatch.setenv("TRACE_DB_ENABLED", "false")
    monkeypatch.setattr(trace_db, "_TRACE_CONFIG", None)
    monkeypatch.setattr(trace_db, "_TRACE_WRITER", None)

    trace_id = trace_db.start_trace(
        trace_id=TRACE_ID,
        user_id="user",
        question="private question",
    )

    assert trace_id == TRACE_ID
    assert trace_db.flush() is True
    assert trace_db._TRACE_WRITER is None


def test_enabled_trace_config_is_lazy_and_missing_credentials_do_not_break_callers(
    monkeypatch,
):
    monkeypatch.setenv("TRACE_DB_ENABLED", "true")
    for key in ("TRACE_DB_USER", "TRACE_DB_PASSWORD", "TRACE_DB_NAME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(trace_db, "_TRACE_CONFIG", None)
    monkeypatch.setattr(trace_db, "start_writer", lambda config=None: None)
    monkeypatch.setattr(trace_db, "_TRACE_WRITER", None)

    trace_id = trace_db.start_trace(trace_id=TRACE_ID)

    assert trace_id == TRACE_ID


def test_start_and_finish_enqueue_expected_sql_and_parameters(monkeypatch):
    writer = use_recording_writer(monkeypatch, capture_content=True)

    trace_db.start_trace(
        trace_id=TRACE_ID,
        user_id="user-1",
        session_id=7,
        persona_id="tutor",
        model="model-x",
        question="Explain tracing",
    )
    trace_db.start_trace(trace_id=TRACE_ID, question="duplicate start")
    trace_db.finish_trace(
        trace_id=TRACE_ID,
        user_id="user-1",
        session_id=7,
        persona_id="tutor",
        model="model-x",
        total_ms=100,
        retrieval_ms=20,
        llm_ms=70,
        status="OK",
        react_rounds=2,
        llm_calls=3,
        tool_calls=4,
        tool_failures=1,
        prompt_tokens=11,
        completion_tokens=12,
    )
    trace_db.finish_trace(trace_id=TRACE_ID, status="ERROR")

    assert len(writer.tasks) == 2
    start_sql, start_params = writer.tasks[0]
    finish_sql, finish_params = writer.tasks[1]
    assert "INSERT INTO agent_traces" in start_sql
    assert len(start_params) == 20
    assert start_params[0] == TRACE_ID
    assert start_params[5] == "Explain tracing"
    assert start_params[9] == "RUNNING"
    assert "UPDATE agent_traces" in finish_sql
    assert finish_params[-1] == TRACE_ID
    assert finish_params[7] == "OK"


def test_event_apis_share_trace_id_and_skip_missing_ids(monkeypatch):
    writer = use_recording_writer(monkeypatch, capture_content=True)
    trace_db.start_trace(trace_id=TRACE_ID)
    writer.tasks.clear()

    assert trace_db.save_retrieval_event(
        trace_id=TRACE_ID,
        query="retrieval query",
        collection="notes",
    )
    assert trace_db.save_llm_call(
        trace_id=TRACE_ID,
        round_number=1,
        call_type="final",
        model="model-x",
    )
    assert trace_db.save_tool_call(
        trace_id=TRACE_ID,
        tool_name="search",
        args_preview={"q": "hello"},
    )
    assert trace_db.save_llm_call(trace_id=None, call_type="ignored") is False
    assert trace_db.save_tool_call(trace_id=None, tool_name="ignored") is False

    assert len(writer.tasks) == 3
    assert all(task[1][0] == TRACE_ID for task in writer.tasks)


def test_content_capture_and_redaction_are_bounded(monkeypatch):
    writer = use_recording_writer(monkeypatch, capture_content=False)
    trace_db.start_trace(trace_id=TRACE_ID, question="do not store this")
    trace_db.save_retrieval_event(
        trace_id=TRACE_ID,
        query="do not store this query",
        collection="notes",
    )
    trace_db.save_tool_call(
        trace_id=TRACE_ID,
        tool_name="call",
        args_preview=json.dumps(
            {
                "password": "pw",
                "token": "tok",
                "api_key": "key",
                "authorization": "auth",
                "secret": "secret-value",
            }
        ),
    )

    assert writer.tasks[0][1][5] is None
    assert writer.tasks[1][1][1] is None
    args_preview = writer.tasks[2][1][-1]
    assert len(args_preview) <= trace_db.MAX_ARGS_PREVIEW_CHARS
    assert all(
        fragment not in args_preview
        for fragment in ('"pw"', '"tok"', '"key"', '"auth"', '"secret-value"')
    )
    assert "REDACTED" in args_preview

    writer.tasks.clear()
    monkeypatch.setattr(trace_db, "_TRACE_CONFIG", enabled_config(capture_content=True))
    trace_db.start_trace(trace_id="b" * 32, question="x" * 10000)
    assert len(writer.tasks[0][1][5]) == trace_db.MAX_CAPTURE_CHARS


def test_queue_full_does_not_block_or_raise(caplog):
    writer = trace_db.TraceWriter(enabled_config(queue_size=1), schema_initializer=lambda _: None)
    assert writer.enqueue("SQL-1", (1,)) is True

    started = time.perf_counter()
    result = writer.enqueue("SQL-2", (2,))
    elapsed = time.perf_counter() - started

    assert result is False
    assert elapsed < 0.1
    assert "trace_writer_queue_full" in caplog.text


def test_database_exception_stays_out_of_calling_thread(monkeypatch):
    class BrokenWriter:
        def enqueue(self, sql, params):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(trace_db, "_TRACE_CONFIG", enabled_config())
    monkeypatch.setattr(trace_db, "_TRACE_WRITER", BrokenWriter())
    monkeypatch.setattr(trace_db, "start_writer", lambda config=None: None)

    assert trace_db.save_llm_call(trace_id=TRACE_ID, call_type="final") is False


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self.executed)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_shutdown_flushes_queued_tasks_within_timeout():
    config = enabled_config(queue_size=4)
    connection = FakeConnection()
    schema_calls = []
    writer = trace_db.TraceWriter(
        config,
        connection_factory=lambda _: connection,
        schema_initializer=lambda conn: schema_calls.append(conn),
    )
    writer.start()
    assert writer.enqueue("INSERT", (1,))

    assert writer.flush(timeout=1.0) is True
    assert writer.shutdown(timeout=1.0) is True
    assert connection.executed == [("INSERT", (1,))]
    assert connection.commits == 1
    assert schema_calls == [connection]
    assert connection.closed is True
