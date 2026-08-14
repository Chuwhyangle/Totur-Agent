"""Non-blocking MySQL writer for Agent observability traces.

This module is the stable facade used by application code.  It never performs
network I/O from ``start_trace`` or any ``save_*`` function; those functions
only enqueue bounded write tasks for a single daemon worker.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any, Callable
import uuid

from dotenv import load_dotenv

from app.config import TraceDbConfig, load_trace_db_config
from app.db.trace_schema import ensure_trace_schema


logger = logging.getLogger(__name__)

MAX_CAPTURE_CHARS = 2048
MAX_ARGS_PREVIEW_CHARS = 1024
RETRY_INITIAL_SECONDS = 0.5
RETRY_MAX_SECONDS = 30.0

INSERT_TRACE_SQL = """
INSERT INTO agent_traces
    (trace_id, user_id, session_id, persona_id, model,
     question, total_ms, retrieval_ms, llm_ms, status,
     react_rounds, llm_calls, tool_calls, tool_failures,
     embed_ms, search_ms, rerank_ms, tool_other_ms,
     prompt_tokens, completion_tokens)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

FINISH_TRACE_SQL = """
UPDATE agent_traces
SET user_id = %s,
    session_id = %s,
    persona_id = %s,
    model = %s,
    total_ms = %s,
    retrieval_ms = %s,
    llm_ms = %s,
    status = %s,
    react_rounds = %s,
    llm_calls = %s,
    tool_calls = %s,
    tool_failures = %s,
    embed_ms = %s,
    search_ms = %s,
    rerank_ms = %s,
    tool_other_ms = %s,
    prompt_tokens = %s,
    completion_tokens = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE trace_id = %s
"""

INSERT_RETRIEVAL_EVENT_SQL = """
INSERT INTO retrieval_events
    (trace_id, query, collection,
     embed_ms, search_ms, rerank_ms, cost_ms,
     top_k, candidate_count, hit_count, top_score, min_score, passed,
     threshold, rerank_applied, rerank_fallback, corpus_fingerprint)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_LLM_CALL_SQL = """
INSERT INTO llm_calls
    (trace_id, round_number, call_type, model,
     prompt_tokens, completion_tokens, total_tokens, cost_ms, finish_reason)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_TOOL_CALL_SQL = """
INSERT INTO tool_calls
    (trace_id, round_number, tool_name, channel, forced, ok, error_code, cost_ms, args_preview)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class _WriteTask:
    sql: str
    params: tuple[Any, ...]


def _connect_mysql(config: TraceDbConfig):
    """Import PyMySQL only when tracing is enabled and a worker connects."""

    import pymysql

    return pymysql.connect(**config.connection_kwargs)


class TraceWriter:
    """One FIFO, bounded, reconnecting writer for a process."""

    def __init__(
        self,
        config: TraceDbConfig,
        *,
        connection_factory: Callable[[TraceDbConfig], Any] = _connect_mysql,
        schema_initializer: Callable[[Any], None] = ensure_trace_schema,
    ) -> None:
        self.config = config
        self.queue: queue.Queue[_WriteTask] = queue.Queue(maxsize=max(1, config.queue_size))
        self._connection_factory = connection_factory
        self._schema_initializer = schema_initializer
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection = None
        self._accepting = True
        self._shutdown_deadline: float | None = None
        self._state_lock = threading.Lock()
        self._pending = False

    @property
    def is_alive(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def pending_count(self) -> int:
        return self.queue.qsize() + int(self._pending)

    def start(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._accepting = True
            self._stop_requested.clear()
            self._shutdown_deadline = None
            self._thread = threading.Thread(
                target=self._run,
                name="trace-db-writer",
                daemon=True,
            )
            self._thread.start()

    def enqueue(self, sql: str, params: tuple[Any, ...]) -> bool:
        with self._state_lock:
            if not self._accepting:
                return False
        try:
            self.queue.put_nowait(_WriteTask(sql=sql, params=params))
            return True
        except queue.Full:
            logger.warning(
                "trace_writer_queue_full queue_size=%s dropped=1",
                self.config.queue_size,
            )
            return False

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for currently queued tasks without stopping the worker."""

        timeout = (
            self.config.shutdown_flush_seconds if timeout is None else max(0.0, timeout)
        )
        deadline = time.monotonic() + timeout
        while self.pending_count:
            if time.monotonic() >= deadline:
                logger.warning(
                    "trace_writer_flush_timeout pending=%s",
                    self.pending_count,
                )
                return False
            time.sleep(0.01)
        return True

    def shutdown(self, timeout: float | None = None) -> bool:
        """Stop after draining as much as possible within ``timeout``."""

        timeout = (
            self.config.shutdown_flush_seconds if timeout is None else max(0.0, timeout)
        )
        with self._state_lock:
            self._accepting = False
            self._shutdown_deadline = time.monotonic() + timeout
            self._stop_requested.set()

        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning(
                "trace_writer_shutdown_timeout pending=%s",
                self.pending_count,
            )
            return False
        return self.pending_count == 0

    def _deadline_reached(self) -> bool:
        deadline = self._shutdown_deadline
        return deadline is not None and time.monotonic() >= deadline

    def _wait_for_retry(self, delay: float) -> None:
        if self._shutdown_deadline is not None:
            remaining = max(0.0, self._shutdown_deadline - time.monotonic())
            delay = min(delay, remaining)
        if delay > 0:
            time.sleep(delay)

    def _close_connection(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                logger.debug("trace_writer_connection_close_failed", exc_info=True)

    def _connect(self) -> bool:
        connection = None
        try:
            connection = self._connection_factory(self.config)
            self._schema_initializer(connection)
            self._connection = connection
            return True
        except Exception as exc:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            self._close_connection()
            logger.warning(
                "trace_writer_connection_failed error_type=%s",
                type(exc).__name__,
            )
            return False

    def _execute(self, task: _WriteTask) -> bool:
        connection = self._connection
        if connection is None:
            return False
        try:
            with connection.cursor() as cursor:
                cursor.execute(task.sql, task.params)
            connection.commit()
            return True
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            self._close_connection()
            logger.warning(
                "trace_writer_write_failed error_type=%s",
                type(exc).__name__,
            )
            return False

    def _discard_pending_tasks(self, pending: _WriteTask | None) -> None:
        if pending is not None:
            self.queue.task_done()
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                return
            else:
                self.queue.task_done()

    def _run(self) -> None:
        pending: _WriteTask | None = None
        retry_delay = RETRY_INITIAL_SECONDS
        try:
            while True:
                if pending is None and self._stop_requested.is_set() and self.queue.empty():
                    break
                if self._deadline_reached():
                    break

                if self._connection is None:
                    if not self._connect():
                        if self._stop_requested.is_set() and self._deadline_reached():
                            break
                        self._wait_for_retry(retry_delay)
                        retry_delay = min(retry_delay * 2, RETRY_MAX_SECONDS)
                        continue
                    retry_delay = RETRY_INITIAL_SECONDS

                if pending is None:
                    try:
                        pending = self.queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    with self._state_lock:
                        self._pending = True

                if self._execute(pending):
                    self.queue.task_done()
                    pending = None
                    with self._state_lock:
                        self._pending = False
                else:
                    # Keep the failed item ahead of later queue items.  It is
                    # retried after the reconnect backoff instead of breaking FIFO.
                    self._wait_for_retry(retry_delay)
                    retry_delay = min(retry_delay * 2, RETRY_MAX_SECONDS)
        finally:
            self._discard_pending_tasks(pending)
            self._close_connection()
            with self._state_lock:
                self._pending = False


_TRACE_CONFIG: TraceDbConfig | None = None
_TRACE_WRITER: TraceWriter | None = None
_TRACE_STATE_LOCK = threading.Lock()
_ACTIVE_TRACE_IDS: set[str] = set()

# Kept as a small compatibility helper for scripts/tests that only inspect the
# legacy connection mapping.  Application writes use TraceDbConfig/TraceWriter.
_DB_CONFIG: dict | None = None


def _get_trace_config() -> TraceDbConfig:
    global _TRACE_CONFIG
    if _TRACE_CONFIG is None:
        with _TRACE_STATE_LOCK:
            if _TRACE_CONFIG is None:
                _TRACE_CONFIG = load_trace_db_config()
    return _TRACE_CONFIG


def load_trace_config() -> TraceDbConfig:
    """Return lazily loaded trace settings."""

    return _get_trace_config()


def load_db_config() -> dict:
    """Load the legacy PyMySQL mapping for explicit administrative scripts.

    Chat writes do not call this function.  Unlike the trace facade, this
    helper remains strict so a manual caller gets a clear configuration error.
    """

    global _DB_CONFIG
    if _DB_CONFIG is None:
        load_dotenv()
        required = {
            "user": os.getenv("TRACE_DB_USER", "").strip(),
            "password": os.getenv("TRACE_DB_PASSWORD", "").strip(),
            "database": os.getenv("TRACE_DB_NAME", "").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"缺少 TRACE_DB_* 配置: {', '.join(missing)}")
        _DB_CONFIG = {
            "host": os.getenv("TRACE_DB_HOST", "127.0.0.1").strip(),
            "port": int(os.getenv("TRACE_DB_PORT", "3306")),
            **required,
            "connect_timeout": float(
                os.getenv("TRACE_DB_CONNECT_TIMEOUT_SECONDS", "3")
            ),
            "charset": "utf8mb4",
        }
    return dict(_DB_CONFIG)


def start_writer(config: TraceDbConfig | None = None) -> None:
    """Start the process writer without waiting for MySQL."""

    global _TRACE_WRITER
    config = config or _get_trace_config()
    if not config.enabled:
        return
    try:
        config.connection_kwargs
    except Exception as exc:
        logger.warning(
            "trace_writer_config_invalid error_type=%s",
            type(exc).__name__,
        )
        return
    with _TRACE_STATE_LOCK:
        if _TRACE_WRITER is None or not _TRACE_WRITER.is_alive:
            _TRACE_WRITER = TraceWriter(config)
            _TRACE_WRITER.start()


def flush(timeout: float | None = None) -> bool:
    writer = _TRACE_WRITER
    if writer is None:
        return True
    return writer.flush(timeout)


def shutdown_writer(timeout: float | None = None) -> bool:
    global _TRACE_WRITER
    writer = _TRACE_WRITER
    if writer is None:
        return True
    result = writer.shutdown(timeout)
    if not writer.is_alive:
        with _TRACE_STATE_LOCK:
            if _TRACE_WRITER is writer:
                _TRACE_WRITER = None
                _ACTIVE_TRACE_IDS.clear()
    return result


def _enqueue(sql: str, params: tuple[Any, ...]) -> bool:
    config = _get_trace_config()
    if not config.enabled:
        return False
    start_writer(config)
    writer = _TRACE_WRITER
    if writer is None:
        return False
    try:
        return writer.enqueue(sql, params)
    except Exception as exc:
        logger.warning("trace_writer_enqueue_failed error_type=%s", type(exc).__name__)
        return False


def _limit_text(value: Any, limit: int = MAX_CAPTURE_CHARS) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


_SENSITIVE_KEY_PARTS = ("password", "token", "api_key", "authorization", "secret")
_SENSITIVE_KEY_RE = re.compile(
    r"(?P<prefix>[\"']?[^\s\"']*(?:password|token|api[_-]?key|authorization|secret)[^\s\"']*[\"']?\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^,}\s]+)",
    re.IGNORECASE,
)


def _mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _SENSITIVE_KEY_PARTS):
                masked[key] = "[REDACTED]"
            else:
                masked[key] = _mask_sensitive(item)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def sanitize_args_preview(value: Any, limit: int = MAX_ARGS_PREVIEW_CHARS) -> str | None:
    """Serialize a bounded preview while masking common credential keys."""

    if value is None:
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        preview = json.dumps(
            _mask_sensitive(parsed),
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        preview = str(value)
        preview = _SENSITIVE_KEY_RE.sub(
            lambda match: f"{match.group('prefix')}[REDACTED]",
            preview,
        )
    return preview[:limit]


def _captured_content(value: Any, config: TraceDbConfig) -> str | None:
    if not config.capture_content:
        return None
    return _limit_text(value)


def start_trace(
    *,
    trace_id: str | None = None,
    user_id: str | None = None,
    session_id: int | None = None,
    persona_id: str | None = None,
    model: str | None = None,
    question: str | None = None,
) -> str:
    """Enqueue one RUNNING root trace and return its 32-character ID."""

    trace_id = trace_id or uuid.uuid4().hex
    config = _get_trace_config()
    if not config.enabled:
        return trace_id

    with _TRACE_STATE_LOCK:
        if trace_id in _ACTIVE_TRACE_IDS:
            return trace_id
        _ACTIVE_TRACE_IDS.add(trace_id)
    _enqueue(
        INSERT_TRACE_SQL,
        (
            trace_id,
            user_id,
            session_id,
            persona_id,
            model,
            _captured_content(question, config),
            None,
            None,
            None,
            "RUNNING",
            0,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    )
    return trace_id


def finish_trace(
    *,
    trace_id: str | None,
    user_id: str | None = None,
    session_id: int | None = None,
    persona_id: str | None = None,
    model: str | None = None,
    total_ms: int | None = None,
    retrieval_ms: int | None = None,
    llm_ms: int | None = None,
    status: str = "OK",
    react_rounds: int | None = None,
    llm_calls: int | None = None,
    tool_calls: int | None = None,
    tool_failures: int | None = None,
    embed_ms: int | None = None,
    search_ms: int | None = None,
    rerank_ms: int | None = None,
    tool_other_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> bool:
    """Enqueue the single terminal update for a root trace."""

    if not trace_id:
        return False
    config = _get_trace_config()
    if not config.enabled:
        return False
    with _TRACE_STATE_LOCK:
        if trace_id not in _ACTIVE_TRACE_IDS:
            return False
        _ACTIVE_TRACE_IDS.remove(trace_id)

    final_status = status if status in {"OK", "ERROR", "CANCELLED"} else "ERROR"
    return _enqueue(
        FINISH_TRACE_SQL,
        (
            user_id,
            session_id,
            persona_id,
            model,
            total_ms,
            retrieval_ms,
            llm_ms,
            final_status,
            react_rounds,
            llm_calls,
            tool_calls,
            tool_failures,
            embed_ms,
            search_ms,
            rerank_ms,
            tool_other_ms,
            prompt_tokens,
            completion_tokens,
            trace_id,
        ),
    )


def save_retrieval_event(
    *,
    trace_id: str | None,
    query: str | None,
    collection: str | None,
    embed_ms: int | None = None,
    search_ms: int | None = None,
    rerank_ms: int | None = None,
    cost_ms: int | None = None,
    top_k: int | None = None,
    candidate_count: int | None = None,
    hit_count: int | None = None,
    top_score: float | None = None,
    min_score: float | None = None,
    passed: int | None = None,
    threshold: float | None = None,
    rerank_applied: int | None = None,
    rerank_fallback: str | None = None,
    corpus_fingerprint: str | None = None,
) -> bool:
    """Enqueue one retrieval event; missing IDs are intentionally skipped."""

    if not trace_id:
        return False
    config = _get_trace_config()
    if not config.enabled:
        return False
    return _enqueue(
        INSERT_RETRIEVAL_EVENT_SQL,
        (
            trace_id,
            _captured_content(query, config),
            collection,
            embed_ms,
            search_ms,
            rerank_ms,
            cost_ms,
            top_k,
            candidate_count,
            hit_count,
            top_score,
            min_score,
            passed,
            threshold,
            rerank_applied,
            rerank_fallback,
            corpus_fingerprint,
        ),
    )


def save_llm_call(
    *,
    trace_id: str | None,
    round_number: int | None = None,
    call_type: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_ms: int | None = None,
    finish_reason: str | None = None,
) -> bool:
    """Enqueue one LLM event; database failures stay outside the request."""

    if not trace_id:
        return False
    if not _get_trace_config().enabled:
        return False
    return _enqueue(
        INSERT_LLM_CALL_SQL,
        (
            trace_id,
            round_number,
            call_type,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_ms,
            finish_reason,
        ),
    )


def save_tool_call(
    *,
    trace_id: str | None,
    round_number: int | None = None,
    tool_name: str | None = None,
    channel: str | None = None,
    forced: int | None = None,
    ok: int | None = None,
    error_code: str | None = None,
    cost_ms: int | None = None,
    args_preview: Any = None,
) -> bool:
    """Enqueue one tool event with a bounded, redacted argument preview."""

    if not trace_id:
        return False
    if not _get_trace_config().enabled:
        return False
    return _enqueue(
        INSERT_TOOL_CALL_SQL,
        (
            trace_id,
            round_number,
            tool_name,
            channel,
            forced,
            ok,
            error_code,
            cost_ms,
            sanitize_args_preview(args_preview),
        ),
    )


def reset_for_tests() -> None:
    """Stop and clear process state for isolated unit tests."""

    global _TRACE_CONFIG, _TRACE_WRITER, _DB_CONFIG
    shutdown_writer(timeout=0.1)
    with _TRACE_STATE_LOCK:
        _TRACE_CONFIG = None
        _DB_CONFIG = None
        _ACTIVE_TRACE_IDS.clear()
