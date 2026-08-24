"""SQLite contract tests for the Workspace foundation migration."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.db import database


EXPECTED_TABLES = {
    "workspaces",
    "workspace_assets",
    "tasks",
    "task_steps",
    "task_asset_refs",
    "artifacts",
    "artifact_sources",
}

EXPECTED_COLUMNS = {
    "workspaces": {
        "id",
        "user_id",
        "name",
        "description",
        "status",
        "created_at",
        "updated_at",
        "archived_at",
    },
    "workspace_assets": {
        "id",
        "workspace_id",
        "original_filename",
        "media_type",
        "size_bytes",
        "storage_key",
        "parsed_storage_key",
        "content_hash",
        "dedupe_key",
        "status",
        "parser_name",
        "parser_version",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "tasks": {
        "id",
        "workspace_id",
        "session_id",
        "trace_id",
        "goal",
        "status",
        "warning_count",
        "error_code",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    },
    "task_steps": {
        "id",
        "task_id",
        "sequence_no",
        "tool_call_id",
        "step_type",
        "tool_name",
        "status",
        "input_summary",
        "output_summary",
        "error_code",
        "started_at",
        "finished_at",
        "created_at",
    },
    "task_asset_refs": {"task_id", "asset_id", "first_step_id", "created_at"},
    "artifacts": {
        "id",
        "workspace_id",
        "task_id",
        "created_by_step_id",
        "artifact_series_id",
        "supersedes_artifact_id",
        "version_number",
        "title",
        "media_type",
        "storage_key",
        "size_bytes",
        "content_hash",
        "creation_key",
        "status",
        "error_code",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "artifact_sources": {"artifact_id", "asset_id", "created_at"},
}


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    return config


def _sqlite_connection(tmp_path):
    return sqlite3.connect(str(tmp_path / "tutor_agent.db"))


def test_workspace_foundation_schema_matches_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "")

    database.initialize_database()

    connection = _sqlite_connection(tmp_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert EXPECTED_TABLES <= tables

        for table, expected_columns in EXPECTED_COLUMNS.items():
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert columns == expected_columns

        session_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chat_sessions)")
        }
        assert "workspace_id" in session_columns

        expected_indexes = {
            "workspaces": {"idx_workspaces_user_status_updated"},
            "workspace_assets": {
                "idx_workspace_assets_workspace_status_created",
                "idx_workspace_assets_status_updated",
            },
            "tasks": {"idx_tasks_workspace_created", "idx_tasks_session_created"},
            "chat_sessions": {"idx_chat_sessions_workspace"},
        }
        for table, names in expected_indexes.items():
            index_names = {
                row[1] for row in connection.execute(f"PRAGMA index_list({table})")
            }
            assert names <= index_names

        foreign_keys = {
            (table, row[3], row[2], row[4], row[6])
            for table in (
                "chat_sessions",
                "workspace_assets",
                "tasks",
                "task_steps",
                "task_asset_refs",
                "artifacts",
                "artifact_sources",
            )
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        }
        assert ("chat_sessions", "workspace_id", "workspaces", "id", "RESTRICT") in foreign_keys
        assert ("workspace_assets", "workspace_id", "workspaces", "id", "RESTRICT") in foreign_keys
        assert ("tasks", "workspace_id", "workspaces", "id", "RESTRICT") in foreign_keys
        assert ("tasks", "session_id", "chat_sessions", "id", "RESTRICT") in foreign_keys
        assert ("task_steps", "task_id", "tasks", "id", "RESTRICT") in foreign_keys
        assert ("task_asset_refs", "task_id", "tasks", "id", "RESTRICT") in foreign_keys
        assert ("task_asset_refs", "asset_id", "workspace_assets", "id", "RESTRICT") in foreign_keys
        assert ("task_asset_refs", "first_step_id", "task_steps", "id", "RESTRICT") in foreign_keys
        assert ("artifacts", "workspace_id", "workspaces", "id", "RESTRICT") in foreign_keys
        assert ("artifacts", "task_id", "tasks", "id", "RESTRICT") in foreign_keys
        assert ("artifacts", "created_by_step_id", "task_steps", "id", "RESTRICT") in foreign_keys
        assert ("artifacts", "supersedes_artifact_id", "artifacts", "id", "RESTRICT") in foreign_keys
        assert ("artifact_sources", "artifact_id", "artifacts", "id", "RESTRICT") in foreign_keys
        assert ("artifact_sources", "asset_id", "workspace_assets", "id", "RESTRICT") in foreign_keys
    finally:
        connection.close()


def test_workspace_status_and_size_constraints_are_enforced(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "")
    database.initialize_database()

    connection = _sqlite_connection(tmp_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO workspaces "
                "(id, user_id, name, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("w-1", "alice", "Workspace", "ACTIVE", "now", "now"),
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO workspaces "
                    "(id, user_id, name, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("w-2", "alice", "Workspace", "INVALID", "now", "now"),
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO workspace_assets "
                    "(id, workspace_id, original_filename, media_type, size_bytes, "
                    "content_hash, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "a-1",
                        "w-1",
                        "file.txt",
                        "text/plain",
                        -1,
                        "h",
                        "STAGING",
                        "now",
                        "now",
                    ),
                )
    finally:
        connection.close()


def test_upgrade_and_downgrade_preserve_old_session_workspace_null(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "")
    database.initialize_database()
    config = _alembic_config()

    command.downgrade(config, "0002_conversations_reply_format")
    connection = _sqlite_connection(tmp_path)
    try:
        connection.execute(
            "INSERT INTO chat_sessions "
            "(user_id, title, persona_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("alice", "Old", "tutor", "now", "now"),
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = _sqlite_connection(tmp_path)
    try:
        row = connection.execute(
            "SELECT workspace_id FROM chat_sessions WHERE user_id = ?",
            ("alice",),
        ).fetchone()
        assert row == (None,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0003_workspace_foundation"
    finally:
        connection.close()

    command.downgrade(config, "0002_conversations_reply_format")
    connection = _sqlite_connection(tmp_path)
    try:
        remaining_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert not EXPECTED_TABLES & remaining_tables
        assert "workspace_id" not in {
            row[1] for row in connection.execute("PRAGMA table_info(chat_sessions)")
        }
    finally:
        connection.close()
