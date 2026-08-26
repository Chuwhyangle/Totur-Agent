"""Add archive state to chat sessions.

Revision ID: 0007_session_lifecycle
Revises: 0006_learning_progress
"""

from alembic import op


revision = "0007_session_lifecycle"
down_revision = "0006_learning_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            """
            ALTER TABLE chat_sessions
              ADD COLUMN archived_at DATETIME(6) NULL,
              ADD KEY idx_chat_sessions_user_archived_updated
                (user_id, archived_at, updated_at DESC, id DESC)
            """
        )
    else:
        op.execute("ALTER TABLE chat_sessions ADD COLUMN archived_at TEXT")
        op.execute(
            """
            CREATE INDEX idx_chat_sessions_user_archived_updated
            ON chat_sessions (user_id, archived_at, updated_at DESC, id DESC)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            """
            ALTER TABLE chat_sessions
              DROP INDEX idx_chat_sessions_user_archived_updated,
              DROP COLUMN archived_at
            """
        )
    else:
        op.execute("DROP INDEX idx_chat_sessions_user_archived_updated")
        op.execute("ALTER TABLE chat_sessions DROP COLUMN archived_at")
