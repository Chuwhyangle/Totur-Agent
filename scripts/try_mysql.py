"""Smoke test the formal Agent trace API against the configured MySQL.

Run with TRACE_DB_ENABLED=true and a dedicated test database:
``python scripts/try_mysql.py``
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logger = logging.getLogger(__name__)


def main() -> int:
    from app.db import trace_db

    config = trace_db.load_trace_config()
    if not config.enabled:
        logger.error("TRACE_DB_ENABLED=true is required for the MySQL smoke test")
        return 2

    try:
        import pymysql

        trace_id = trace_db.start_trace(
            user_id="trace-smoke-user",
            persona_id="tutor",
            model="trace-smoke-model",
            question="trace smoke question",
        )
        trace_db.save_retrieval_event(
            trace_id=trace_id,
            query="trace smoke query",
            collection="smoke",
            top_k=3,
            candidate_count=3,
            hit_count=1,
            passed=1,
        )
        trace_db.save_llm_call(
            trace_id=trace_id,
            round_number=1,
            call_type="final",
            model="trace-smoke-model",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost_ms=50,
            finish_reason="stop",
        )
        trace_db.save_tool_call(
            trace_id=trace_id,
            round_number=1,
            tool_name="trace_smoke_tool",
            channel="internal",
            ok=1,
            cost_ms=5,
            args_preview={"message": "bounded smoke preview"},
        )
        trace_db.finish_trace(
            trace_id=trace_id,
            user_id="trace-smoke-user",
            persona_id="tutor",
            model="trace-smoke-model",
            total_ms=100,
            retrieval_ms=15,
            llm_ms=50,
            status="OK",
            react_rounds=1,
            llm_calls=1,
            tool_calls=1,
            tool_failures=0,
            prompt_tokens=10,
            completion_tokens=20,
        )

        if not trace_db.flush(config.shutdown_flush_seconds):
            logger.error("trace smoke flush timed out")
            return 1

        connection = pymysql.connect(**config.connection_kwargs)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM agent_traces WHERE trace_id = %s",
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
                        f"SELECT COUNT(*) FROM {table_name} WHERE trace_id = %s",
                        (trace_id,),
                    )
                    counts[table_name] = cursor.fetchone()[0]
        finally:
            connection.close()

        if root is None or root[0] != "OK":
            raise RuntimeError("root trace was not written with status OK")
        if counts != {
            "retrieval_events": 1,
            "llm_calls": 1,
            "tool_calls": 1,
        }:
            raise RuntimeError("trace child event counts do not match")
        logger.info("trace smoke passed trace_id=%s", trace_id)
        return 0
    except Exception as exc:
        logger.error("trace smoke failed error_type=%s", type(exc).__name__)
        return 1
    finally:
        trace_db.shutdown_writer(timeout=config.shutdown_flush_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
