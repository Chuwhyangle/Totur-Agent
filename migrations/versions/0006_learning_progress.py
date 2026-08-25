"""user-level learning progress for subject workspaces.

Revision ID: 0006_learning_progress
Revises: 0005_knowledge_documents
"""

from alembic import op


revision = "0006_learning_progress"
down_revision = "0005_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        _upgrade_mysql()
    else:
        _upgrade_sqlite()


def downgrade() -> None:
    op.execute("DROP TABLE learning_progress")


def _upgrade_mysql() -> None:
    op.execute(
        """
        CREATE TABLE learning_progress (
          id          BIGINT NOT NULL AUTO_INCREMENT,
          user_id     VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          subject     VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          topic       VARCHAR(120) COLLATE utf8mb4_0900_bin NOT NULL,
          level       TINYINT NOT NULL DEFAULT 0,
          status      VARCHAR(24) COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'learning',
          evidence    TEXT NULL,
          next_step   VARCHAR(500) NULL,
          source      VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'manual',
          updated_at  DATETIME(6) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_learning_progress_user_subject_topic (user_id, subject, topic),
          KEY idx_learning_progress_user_subject_updated
            (user_id, subject, updated_at DESC),
          CONSTRAINT ck_learning_progress_level CHECK (level BETWEEN 0 AND 3),
          CONSTRAINT ck_learning_progress_status CHECK (
            status IN ('not_started', 'learning', 'needs_practice', 'mastered')
          ),
          CONSTRAINT ck_learning_progress_source CHECK (source IN ('manual', 'agent'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )


def _upgrade_sqlite() -> None:
    op.execute(
        """
        CREATE TABLE learning_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            topic TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 3),
            status TEXT NOT NULL DEFAULT 'learning' CHECK (
                status IN ('not_started', 'learning', 'needs_practice', 'mastered')
            ),
            evidence TEXT,
            next_step TEXT,
            source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'agent')),
            updated_at TEXT NOT NULL,
            UNIQUE (user_id, subject, topic)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_learning_progress_user_subject_updated
        ON learning_progress (user_id, subject, updated_at DESC)
        """
    )
