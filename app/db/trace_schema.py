"""Idempotent MySQL schema management for Agent observability traces.

The connection is created with the configured trace database selected.  No
business tables are created or altered here.
"""

from collections.abc import Mapping


CREATE_TABLE_SQL: Mapping[str, str] = {
    "agent_traces": """
        CREATE TABLE IF NOT EXISTS agent_traces (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id CHAR(32) NOT NULL,
            user_id VARCHAR(64),
            session_id BIGINT,
            persona_id VARCHAR(64),
            model VARCHAR(128),
            question TEXT,
            total_ms INT,
            retrieval_ms INT,
            llm_ms INT,
            status VARCHAR(16) NOT NULL DEFAULT 'RUNNING',
            react_rounds INT DEFAULT 0,
            llm_calls INT DEFAULT 0,
            tool_calls INT DEFAULT 0,
            tool_failures INT DEFAULT 0,
            embed_ms INT,
            search_ms INT,
            rerank_ms INT,
            tool_other_ms INT,
            prompt_tokens INT,
            completion_tokens INT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "retrieval_events": """
        CREATE TABLE IF NOT EXISTS retrieval_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id CHAR(32),
            query TEXT,
            collection VARCHAR(64),
            embed_ms INT,
            search_ms INT,
            rerank_ms INT,
            cost_ms INT,
            top_k INT,
            candidate_count INT,
            hit_count INT,
            top_score FLOAT,
            min_score FLOAT,
            passed TINYINT,
            threshold FLOAT,
            rerank_applied TINYINT,
            rerank_fallback VARCHAR(64),
            corpus_fingerprint VARCHAR(128),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "llm_calls": """
        CREATE TABLE IF NOT EXISTS llm_calls (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id CHAR(32),
            round_number INT,
            call_type VARCHAR(16),
            model VARCHAR(128),
            prompt_tokens INT,
            completion_tokens INT,
            total_tokens INT,
            cost_ms INT,
            finish_reason VARCHAR(32),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "tool_calls": """
        CREATE TABLE IF NOT EXISTS tool_calls (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trace_id CHAR(32),
            round_number INT,
            tool_name VARCHAR(64),
            channel VARCHAR(16),
            forced TINYINT DEFAULT 0,
            ok TINYINT,
            error_code VARCHAR(64),
            cost_ms INT,
            args_preview VARCHAR(1024),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


COLUMN_DEFINITIONS: Mapping[str, Mapping[str, str]] = {
    "agent_traces": {
        "trace_id": "CHAR(32) NULL",
        "user_id": "VARCHAR(64) NULL",
        "session_id": "BIGINT NULL",
        "persona_id": "VARCHAR(64) NULL",
        "model": "VARCHAR(128) NULL",
        "question": "TEXT NULL",
        "total_ms": "INT NULL",
        "retrieval_ms": "INT NULL",
        "llm_ms": "INT NULL",
        "status": "VARCHAR(16) NULL DEFAULT 'RUNNING'",
        "react_rounds": "INT NULL DEFAULT 0",
        "llm_calls": "INT NULL DEFAULT 0",
        "tool_calls": "INT NULL DEFAULT 0",
        "tool_failures": "INT NULL DEFAULT 0",
        "embed_ms": "INT NULL",
        "search_ms": "INT NULL",
        "rerank_ms": "INT NULL",
        "tool_other_ms": "INT NULL",
        "prompt_tokens": "INT NULL",
        "completion_tokens": "INT NULL",
        "created_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "retrieval_events": {
        "trace_id": "CHAR(32) NULL",
        "query": "TEXT NULL",
        "collection": "VARCHAR(64) NULL",
        "embed_ms": "INT NULL",
        "search_ms": "INT NULL",
        "rerank_ms": "INT NULL",
        "cost_ms": "INT NULL",
        "top_k": "INT NULL",
        "candidate_count": "INT NULL",
        "hit_count": "INT NULL",
        "top_score": "FLOAT NULL",
        "min_score": "FLOAT NULL",
        "passed": "TINYINT NULL",
        "threshold": "FLOAT NULL",
        "rerank_applied": "TINYINT NULL",
        "rerank_fallback": "VARCHAR(64) NULL",
        "corpus_fingerprint": "VARCHAR(128) NULL",
        "created_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP",
    },
    "llm_calls": {
        "trace_id": "CHAR(32) NULL",
        "round_number": "INT NULL",
        "call_type": "VARCHAR(16) NULL",
        "model": "VARCHAR(128) NULL",
        "prompt_tokens": "INT NULL",
        "completion_tokens": "INT NULL",
        "total_tokens": "INT NULL",
        "cost_ms": "INT NULL",
        "finish_reason": "VARCHAR(32) NULL",
        "created_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP",
    },
    "tool_calls": {
        "trace_id": "CHAR(32) NULL",
        "round_number": "INT NULL",
        "tool_name": "VARCHAR(64) NULL",
        "channel": "VARCHAR(16) NULL",
        "forced": "TINYINT NULL DEFAULT 0",
        "ok": "TINYINT NULL",
        "error_code": "VARCHAR(64) NULL",
        "cost_ms": "INT NULL",
        "args_preview": "VARCHAR(1024) NULL",
        "created_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP",
    },
}


INDEX_DEFINITIONS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "agent_traces": {
        "uq_agent_traces_trace_id": ("trace_id",),
        "idx_agent_traces_created_at": ("created_at",),
    },
    "retrieval_events": {
        "idx_retrieval_events_trace_id": ("trace_id",),
        "idx_retrieval_events_created_at": ("created_at",),
    },
    "llm_calls": {
        "idx_llm_calls_trace_id": ("trace_id",),
        "idx_llm_calls_created_at": ("created_at",),
    },
    "tool_calls": {
        "idx_tool_calls_trace_id": ("trace_id",),
        "idx_tool_calls_created_at": ("created_at",),
        "idx_tool_calls_name_created": ("tool_name", "created_at"),
    },
}


def _existing_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cursor.fetchall()}


def _existing_indexes(cursor, table_name: str) -> dict[str, tuple[bool, tuple[str, ...]]]:
    cursor.execute(
        """
        SELECT index_name, non_unique, column_name, seq_in_index
        FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s
        ORDER BY index_name, seq_in_index
        """,
        (table_name,),
    )
    indexes: dict[str, tuple[bool, tuple[str, ...]]] = {}
    grouped: dict[str, list[tuple[int, str, bool]]] = {}
    for index_name, non_unique, column_name, seq_in_index in cursor.fetchall():
        grouped.setdefault(index_name, []).append(
            (seq_in_index, column_name, not bool(non_unique))
        )
    for index_name, columns in grouped.items():
        ordered = sorted(columns)
        indexes[index_name] = (
            ordered[0][2],
            tuple(column_name for _, column_name, _ in ordered),
        )
    return indexes


def _has_unique_columns(
    indexes: Mapping[str, tuple[bool, tuple[str, ...]]], columns: tuple[str, ...]
) -> bool:
    return any(unique and index_columns == columns for unique, index_columns in indexes.values())


def initialize_trace_schema(connection) -> None:
    """Create and upgrade only the four trace tables on ``connection``.

    Existing rows are never deleted.  Missing columns and indexes are added
    individually so the function also upgrades the historical 001-005 schema.
    """

    with connection.cursor() as cursor:
        for table_name, create_sql in CREATE_TABLE_SQL.items():
            cursor.execute(create_sql)

        for table_name, definitions in COLUMN_DEFINITIONS.items():
            columns = _existing_columns(cursor, table_name)
            for column_name, definition in definitions.items():
                if column_name not in columns:
                    cursor.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )

        for table_name, definitions in INDEX_DEFINITIONS.items():
            indexes = _existing_indexes(cursor, table_name)
            for index_name, columns in definitions.items():
                if index_name in indexes:
                    continue
                if table_name == "agent_traces" and columns == ("trace_id",):
                    if _has_unique_columns(indexes, columns):
                        continue
                    cursor.execute(
                        f"CREATE UNIQUE INDEX {index_name} ON {table_name} (trace_id)"
                    )
                else:
                    column_sql = ", ".join(columns)
                    cursor.execute(
                        f"CREATE INDEX {index_name} ON {table_name} ({column_sql})"
                    )

    connection.commit()


# Short alias used by the writer and CLI.
ensure_trace_schema = initialize_trace_schema
