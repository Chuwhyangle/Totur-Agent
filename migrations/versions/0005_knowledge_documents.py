"""knowledge document metadata for the independent user_documents index.

Revision ID: 0005_knowledge_documents
Revises: 0004_custom_personas_and_agent_instructions
"""

from alembic import op


revision = "0005_knowledge_documents"
down_revision = "0004_custom_personas_and_agent_instructions"
branch_labels = None
depends_on = None


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


def _upgrade_mysql() -> None:
    op.execute(
        """
        CREATE TABLE knowledge_documents (
          id                CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          user_id           VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          original_filename VARCHAR(255) NOT NULL,
          media_type        VARCHAR(127) COLLATE utf8mb4_0900_bin NOT NULL,
          size_bytes        BIGINT NOT NULL,
          storage_key       VARCHAR(512) COLLATE utf8mb4_0900_bin NULL,
          file_sha256       CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          text_sha256       CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
          dedupe_key        CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
          version_no        INT NOT NULL DEFAULT 1,
          status            VARCHAR(24) COLLATE utf8mb4_0900_bin NOT NULL,
          page_count        INT NULL,
          chunk_count       INT NULL,
          parser_name       VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          parser_version    VARCHAR(32) COLLATE utf8mb4_0900_bin NULL,
          error_code        VARCHAR(64) COLLATE utf8mb4_0900_bin NULL,
          error_message     VARCHAR(512) NULL,
          created_at        DATETIME(6) NOT NULL,
          updated_at        DATETIME(6) NOT NULL,
          deleted_at        DATETIME(6) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_knowledge_documents_dedupe (user_id, dedupe_key),
          KEY idx_knowledge_documents_user_status (user_id, status, created_at DESC),
          KEY idx_knowledge_documents_logical (user_id, original_filename, version_no DESC),
          KEY idx_knowledge_documents_text_hash (user_id, text_sha256),
          CONSTRAINT ck_knowledge_documents_size CHECK (size_bytes >= 0),
          CONSTRAINT ck_knowledge_documents_version CHECK (version_no >= 1),
          CONSTRAINT ck_knowledge_documents_status CHECK (status IN (
            'UPLOADED', 'PARSING', 'CHUNKING', 'EMBEDDING', 'READY',
            'FAILED', 'DELETING', 'DELETED'
          ))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )


def _downgrade_mysql() -> None:
    op.execute("DROP TABLE knowledge_documents")


def _upgrade_sqlite() -> None:
    op.execute(
        """
        CREATE TABLE knowledge_documents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            storage_key TEXT,
            file_sha256 TEXT NOT NULL,
            text_sha256 TEXT,
            dedupe_key TEXT,
            version_no INTEGER NOT NULL DEFAULT 1 CHECK (version_no >= 1),
            status TEXT NOT NULL CHECK (status IN (
                'UPLOADED', 'PARSING', 'CHUNKING', 'EMBEDDING', 'READY',
                'FAILED', 'DELETING', 'DELETED'
            )),
            page_count INTEGER,
            chunk_count INTEGER,
            parser_name TEXT,
            parser_version TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            UNIQUE (user_id, dedupe_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_documents_user_status
        ON knowledge_documents (user_id, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_documents_logical
        ON knowledge_documents (user_id, original_filename, version_no DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_knowledge_documents_text_hash
        ON knowledge_documents (user_id, text_sha256)
        """
    )


def _downgrade_sqlite() -> None:
    op.execute("DROP TABLE knowledge_documents")
