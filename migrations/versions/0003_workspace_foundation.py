"""workspace foundation schema.

Adds the Workspace ownership boundary and the data contracts for future assets,
tasks, steps, and artifacts.  Business services for those future resources are
intentionally not part of this migration.

Revision ID: 0003_workspace_foundation
Revises: 0002_conversations_reply_format
Create Date: 2026-08-24

"""

from alembic import op


revision = "0003_workspace_foundation"
down_revision = "0002_conversations_reply_format"
branch_labels = None
depends_on = None


_WORKSPACE_TABLES_DROP_ORDER = (
    "artifact_sources",
    "artifacts",
    "task_asset_refs",
    "task_steps",
    "tasks",
    "workspace_assets",
)


def _is_mysql(bind) -> bool:
    return bind.dialect.name == "mysql"


def upgrade() -> None:
    bind = op.get_bind()
    if _is_mysql(bind):
        _upgrade_mysql()
    else:
        _upgrade_sqlite()


def downgrade() -> None:
    bind = op.get_bind()
    if _is_mysql(bind):
        _downgrade_mysql()
    else:
        _downgrade_sqlite()


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------


def _upgrade_mysql() -> None:
    op.execute(
        """
        CREATE TABLE workspaces (
          id          CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          user_id     VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          name        VARCHAR(120) NOT NULL,
          description TEXT NULL,
          status      VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL,
          created_at  DATETIME(6) NOT NULL,
          updated_at  DATETIME(6) NOT NULL,
          archived_at DATETIME(6) NULL,
          PRIMARY KEY (id),
          KEY idx_workspaces_user_status_updated
            (user_id, status, updated_at DESC),
          CONSTRAINT ck_workspaces_status
            CHECK (status IN ('ACTIVE', 'ARCHIVED'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        ALTER TABLE chat_sessions
          ADD COLUMN workspace_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
          ADD KEY idx_chat_sessions_workspace (workspace_id),
          ADD CONSTRAINT fk_chat_sessions_workspace
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_assets (
          id                  CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          workspace_id        CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          original_filename   VARCHAR(255) NOT NULL,
          media_type          VARCHAR(127) COLLATE utf8mb4_0900_bin NOT NULL,
          size_bytes          BIGINT NOT NULL,
          storage_key         VARCHAR(512) COLLATE utf8mb4_0900_bin NULL,
          parsed_storage_key  VARCHAR(512) COLLATE utf8mb4_0900_bin NULL,
          content_hash        CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          dedupe_key          CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
          status              VARCHAR(24) COLLATE utf8mb4_0900_bin NOT NULL,
          parser_name         VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          parser_version      VARCHAR(32) COLLATE utf8mb4_0900_bin NULL,
          error_code          VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          error_message       VARCHAR(512) NULL,
          created_at          DATETIME(6) NOT NULL,
          updated_at          DATETIME(6) NOT NULL,
          deleted_at          DATETIME(6) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_workspace_assets_dedupe (workspace_id, dedupe_key),
          KEY idx_workspace_assets_workspace_status_created
            (workspace_id, status, created_at DESC),
          KEY idx_workspace_assets_status_updated (status, updated_at DESC),
          CONSTRAINT fk_workspace_assets_workspace
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT,
          CONSTRAINT ck_workspace_assets_size CHECK (size_bytes >= 0),
          CONSTRAINT ck_workspace_assets_status CHECK (status IN (
            'STAGING', 'PROCESSING', 'READY', 'FAILED', 'DELETING', 'DELETED'
          ))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE tasks (
          id            CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          workspace_id  CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          session_id    BIGINT NOT NULL,
          trace_id      CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          goal          VARCHAR(500) NOT NULL,
          status        VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL,
          warning_count INT NOT NULL DEFAULT 0,
          error_code    VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          started_at    DATETIME(6) NOT NULL,
          finished_at   DATETIME(6) NULL,
          created_at    DATETIME(6) NOT NULL,
          updated_at    DATETIME(6) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_tasks_trace (trace_id),
          KEY idx_tasks_workspace_created (workspace_id, created_at DESC),
          KEY idx_tasks_session_created (session_id, created_at DESC),
          CONSTRAINT fk_tasks_workspace
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT,
          CONSTRAINT fk_tasks_session
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE RESTRICT,
          CONSTRAINT ck_tasks_status CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
          CONSTRAINT ck_tasks_warning_count CHECK (warning_count >= 0)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE task_steps (
          id             BIGINT NOT NULL AUTO_INCREMENT,
          task_id        CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          sequence_no    INT NOT NULL,
          tool_call_id   VARCHAR(128) COLLATE utf8mb4_0900_bin NOT NULL,
          step_type      VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          tool_name      VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          status         VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL,
          input_summary  VARCHAR(1000) NULL,
          output_summary VARCHAR(1000) NULL,
          error_code     VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          started_at     DATETIME(6) NOT NULL,
          finished_at    DATETIME(6) NULL,
          created_at     DATETIME(6) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_task_steps_sequence (task_id, sequence_no),
          UNIQUE KEY uk_task_steps_tool_call (task_id, tool_call_id),
          CONSTRAINT fk_task_steps_task
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
          CONSTRAINT ck_task_steps_status CHECK (
            status IN ('RUNNING', 'SUCCEEDED', 'FAILED')
          )
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE task_asset_refs (
          task_id       CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          asset_id      CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          first_step_id BIGINT NOT NULL,
          created_at    DATETIME(6) NOT NULL,
          PRIMARY KEY (task_id, asset_id),
          CONSTRAINT fk_task_asset_refs_task
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
          CONSTRAINT fk_task_asset_refs_asset
            FOREIGN KEY (asset_id) REFERENCES workspace_assets(id) ON DELETE RESTRICT,
          CONSTRAINT fk_task_asset_refs_first_step
            FOREIGN KEY (first_step_id) REFERENCES task_steps(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE artifacts (
          id                    CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          workspace_id          CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          task_id               CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          created_by_step_id    BIGINT NOT NULL,
          artifact_series_id    CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          supersedes_artifact_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
          version_number        INT NOT NULL,
          title                 VARCHAR(255) NOT NULL,
          media_type            VARCHAR(127) COLLATE utf8mb4_0900_bin NOT NULL,
          storage_key            VARCHAR(512) COLLATE utf8mb4_0900_bin NULL,
          size_bytes            BIGINT NULL,
          content_hash          CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
          creation_key          VARCHAR(255) COLLATE utf8mb4_0900_bin NOT NULL,
          status                VARCHAR(16) COLLATE utf8mb4_0900_bin NOT NULL,
          error_code            VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          created_at            DATETIME(6) NOT NULL,
          updated_at            DATETIME(6) NOT NULL,
          deleted_at            DATETIME(6) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_artifacts_creation_key (creation_key),
          UNIQUE KEY uk_artifacts_series_version (artifact_series_id, version_number),
          UNIQUE KEY uk_artifacts_supersedes (supersedes_artifact_id),
          CONSTRAINT fk_artifacts_workspace
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT,
          CONSTRAINT fk_artifacts_task
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
          CONSTRAINT fk_artifacts_created_by_step
            FOREIGN KEY (created_by_step_id) REFERENCES task_steps(id) ON DELETE RESTRICT,
          CONSTRAINT fk_artifacts_supersedes
            FOREIGN KEY (supersedes_artifact_id) REFERENCES artifacts(id) ON DELETE RESTRICT,
          CONSTRAINT ck_artifacts_size CHECK (size_bytes IS NULL OR size_bytes >= 0),
          CONSTRAINT ck_artifacts_version CHECK (version_number >= 1),
          CONSTRAINT ck_artifacts_status CHECK (status IN ('CREATING', 'READY', 'FAILED'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE artifact_sources (
          artifact_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          asset_id    CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          created_at  DATETIME(6) NOT NULL,
          PRIMARY KEY (artifact_id, asset_id),
          CONSTRAINT fk_artifact_sources_artifact
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE RESTRICT,
          CONSTRAINT fk_artifact_sources_asset
            FOREIGN KEY (asset_id) REFERENCES workspace_assets(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )


def _downgrade_mysql() -> None:
    for table in _WORKSPACE_TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE {table}")
    op.execute(
        """
        ALTER TABLE chat_sessions
          DROP FOREIGN KEY fk_chat_sessions_workspace,
          DROP INDEX idx_chat_sessions_workspace,
          DROP COLUMN workspace_id
        """
    )
    op.execute("DROP TABLE workspaces")


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def _upgrade_sqlite() -> None:
    op.execute(
        """
        CREATE TABLE workspaces (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT
        )
        """
    )
    op.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE RESTRICT
        """
    )
    op.execute(
        "CREATE INDEX idx_chat_sessions_workspace ON chat_sessions (workspace_id)"
    )
    op.execute(
        """
        CREATE INDEX idx_workspaces_user_status_updated
        ON workspaces (user_id, status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_assets (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            original_filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            storage_key TEXT,
            parsed_storage_key TEXT,
            content_hash TEXT NOT NULL,
            dedupe_key TEXT,
            status TEXT NOT NULL CHECK (status IN (
                'STAGING', 'PROCESSING', 'READY', 'FAILED', 'DELETING', 'DELETED'
            )),
            parser_name TEXT,
            parser_version TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE (workspace_id, dedupe_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_workspace_assets_workspace_status_created
        ON workspace_assets (workspace_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_workspace_assets_status_updated
        ON workspace_assets (status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE RESTRICT,
            trace_id TEXT NOT NULL UNIQUE,
            goal TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
            error_code TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_tasks_workspace_created ON tasks (workspace_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_tasks_session_created ON tasks (session_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE task_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            sequence_no INTEGER NOT NULL,
            tool_call_id TEXT NOT NULL,
            step_type TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
            input_summary TEXT,
            output_summary TEXT,
            error_code TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (task_id, sequence_no),
            UNIQUE (task_id, tool_call_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE task_asset_refs (
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            asset_id TEXT NOT NULL REFERENCES workspace_assets(id) ON DELETE RESTRICT,
            first_step_id INTEGER NOT NULL REFERENCES task_steps(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (task_id, asset_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE artifacts (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
            created_by_step_id INTEGER NOT NULL REFERENCES task_steps(id) ON DELETE RESTRICT,
            artifact_series_id TEXT NOT NULL,
            supersedes_artifact_id TEXT REFERENCES artifacts(id) ON DELETE RESTRICT,
            version_number INTEGER NOT NULL CHECK (version_number >= 1),
            title TEXT NOT NULL,
            media_type TEXT NOT NULL,
            storage_key TEXT,
            size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
            content_hash TEXT,
            creation_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('CREATING', 'READY', 'FAILED')),
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE (artifact_series_id, version_number),
            UNIQUE (supersedes_artifact_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE artifact_sources (
            artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
            asset_id TEXT NOT NULL REFERENCES workspace_assets(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (artifact_id, asset_id)
        )
        """
    )


def _downgrade_sqlite() -> None:
    for table in _WORKSPACE_TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP INDEX idx_chat_sessions_workspace")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN workspace_id")
    op.execute("DROP TABLE workspaces")
