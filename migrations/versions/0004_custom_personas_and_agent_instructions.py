"""custom personas and workspace agent instructions.

Revision ID: 0004_custom_personas_and_agent_instructions
Revises: 0003_workspace_foundation
"""

from alembic import op


revision = "0004_custom_personas_and_agent_instructions"
down_revision = "0003_workspace_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        # Alembic creates this table with VARCHAR(32) by default, but this
        # revision id (and later ones) is longer than 32 characters.
        op.execute(
            "ALTER TABLE alembic_version "
            "MODIFY version_num VARCHAR(255) NOT NULL"
        )
        op.execute(
            """
            CREATE TABLE custom_personas (
              id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
              user_id VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
              name VARCHAR(100) NOT NULL,
              description VARCHAR(500) NOT NULL,
              system_prompt TEXT NOT NULL,
              status VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'ACTIVE',
              created_at DATETIME(6) NOT NULL,
              updated_at DATETIME(6) NOT NULL,
              PRIMARY KEY (id),
              KEY idx_custom_personas_user_status_updated (user_id, status, updated_at DESC),
              CONSTRAINT ck_custom_personas_status CHECK (status IN ('ACTIVE', 'DISABLED'))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
            """
        )
        op.execute(
            """ALTER TABLE workspaces
               ADD COLUMN agent_instructions TEXT NULL,
               ADD COLUMN agent_instructions_version INT NOT NULL DEFAULT 0"""
        )
    else:
        op.execute(
            """
            CREATE TABLE custom_personas (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL,
              system_prompt TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        op.execute(
            "CREATE INDEX idx_custom_personas_user_status_updated "
            "ON custom_personas (user_id, status, updated_at DESC)"
        )
        op.execute(
            "ALTER TABLE workspaces ADD COLUMN agent_instructions TEXT"
        )
        op.execute(
            "ALTER TABLE workspaces ADD COLUMN agent_instructions_version INTEGER NOT NULL DEFAULT 0"
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP TABLE custom_personas")
    op.execute("ALTER TABLE workspaces DROP COLUMN agent_instructions")
    op.execute("ALTER TABLE workspaces DROP COLUMN agent_instructions_version")
