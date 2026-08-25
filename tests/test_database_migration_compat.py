"""Alembic 接管后的存量库兼容测试。

覆盖场景：Alembic 之前由旧 DDL 创建的本地库没有 alembic_version 表，
initialize_database() 必须先按 0001 打点再增量升级，不能重建已有表。
"""

import sqlite3

from app.db import database
from app.db.models import CONVERSATIONS_TABLE


def _use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _create_pre_alembic_conversations_table(tmp_path):
    """模拟旧代码 DDL 创建的 conversations 表（无 alembic_version）。"""

    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    try:
        connection.execute(
            """
            CREATE TABLE chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                persona_id TEXT NOT NULL DEFAULT 'tutor',
                subject TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE {CONVERSATIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                reply_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO chat_sessions "
            "(user_id, title, persona_id, created_at, updated_at) "
            "VALUES ('alice', '旧会话', 'tutor', '2026-01-01T00:00:00', "
            "'2026-01-01T00:00:00')"
        )
        connection.execute(
            "INSERT INTO conversations "
            "(session_id, user_id, message, reply_json, created_at) "
            "VALUES (1, 'alice', '旧问题', ?, '2026-01-01T00:00:00')",
            ('{"answer": "旧回答"}',),
        )
        connection.commit()
    finally:
        connection.close()


def test_initialize_database_stamps_pre_alembic_database_then_upgrades(
    monkeypatch,
    tmp_path,
):
    _use_temp_database(monkeypatch, tmp_path)
    _create_pre_alembic_conversations_table(tmp_path)

    database.initialize_database()

    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
        }
        assert "reply_format" in columns

        row = connection.execute(
            f"SELECT message, reply_json, reply_format "
            f"FROM {CONVERSATIONS_TABLE}"
        ).fetchone()
        assert row["message"] == "旧问题"
        assert row["reply_json"] == '{"answer": "旧回答"}'
        assert row["reply_format"] == "json_v1"

        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()["version_num"]
        assert version == "0005_knowledge_documents"
    finally:
        connection.close()


def test_initialize_database_stamping_is_idempotent(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    _create_pre_alembic_conversations_table(tmp_path)

    database.initialize_database()
    database.initialize_database()

    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    try:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {CONVERSATIONS_TABLE}"
        ).fetchone()[0]
        assert count == 1
    finally:
        connection.close()


def test_initialize_database_recovers_from_empty_alembic_version_table(
    monkeypatch,
    tmp_path,
):
    """失败的升级会留下空 alembic_version 表，必须也能自动打点恢复。"""

    _use_temp_database(monkeypatch, tmp_path)
    _create_pre_alembic_conversations_table(tmp_path)
    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    try:
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.commit()
    finally:
        connection.close()

    database.initialize_database()

    connection = sqlite3.connect(str(tmp_path / "tutor_agent.db"))
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
        }
        assert "reply_format" in columns
        assert connection.execute(
            f"SELECT reply_format FROM {CONVERSATIONS_TABLE}"
        ).fetchone()["reply_format"] == "json_v1"
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()["version_num"] == "0005_knowledge_documents"
    finally:
        connection.close()
