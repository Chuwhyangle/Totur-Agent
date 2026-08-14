"""Unit tests for the target-database-safe trace schema initializer."""

from app.db import trace_schema


def test_fresh_schema_contains_all_trace_tables_and_columns():
    assert set(trace_schema.CREATE_TABLE_SQL) == {
        "agent_traces",
        "retrieval_events",
        "llm_calls",
        "tool_calls",
    }
    assert set(trace_schema.COLUMN_DEFINITIONS["agent_traces"]) >= {
        "trace_id",
        "user_id",
        "session_id",
        "persona_id",
        "model",
        "question",
        "total_ms",
        "retrieval_ms",
        "llm_ms",
        "status",
        "react_rounds",
        "llm_calls",
        "tool_calls",
        "tool_failures",
        "embed_ms",
        "search_ms",
        "rerank_ms",
        "tool_other_ms",
        "prompt_tokens",
        "completion_tokens",
        "created_at",
        "updated_at",
    }
    assert "CHAR(32)" in trace_schema.CREATE_TABLE_SQL["agent_traces"]
    assert "uq_agent_traces_trace_id" in trace_schema.INDEX_DEFINITIONS["agent_traces"]


def test_schema_sql_does_not_select_a_business_database():
    sql = "\n".join(trace_schema.CREATE_TABLE_SQL.values())
    assert "tutor_agent" not in sql
    assert "USE " not in sql.upper()


def test_unique_trace_index_is_skipped_when_an_equivalent_unique_index_exists():
    indexes = {
        "legacy_unique_trace": (True, ("trace_id",)),
        "created": (False, ("created_at",)),
    }
    assert trace_schema._has_unique_columns(indexes, ("trace_id",))
