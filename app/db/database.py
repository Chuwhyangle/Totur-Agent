"""SQLite connection and schema initialization."""

from pathlib import Path
import sqlite3

from app.db.models import CONVERSATIONS_TABLE


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "tutor_agent.db"


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection for the app database."""

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database() -> None:
    """Create database tables if they do not already exist."""

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {CONVERSATIONS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        reply_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """

    connection = get_connection()
    try:
        connection.execute(create_table_sql)
        connection.commit()
    finally:
        connection.close()
