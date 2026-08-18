"""initial schema: 7 tables for tutor_agent

目标 schema 手写（不从 SQLite autogenerate）。按方言分两套 DDL：
- MySQL：utf8mb4 + DATETIME(6) + JSON + 按列语义 collation（见数据库重构文档 §3.B3）
- SQLite：等价结构，保持阶段 A~B 开发与测试全绿

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-18

"""

from alembic import op

revision = "0001_initial"
down_revision = None
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


# ---------------------------------------------------------------------------
# MySQL（目标 schema，逐字对应数据库重构文档 §3.B3）
# ---------------------------------------------------------------------------

_MYSQL_TABLES_DROP_ORDER = (
    "journal_entries",
    "documents",
    "public_job_descriptions",
    "interview_jds",
    "session_summaries",
    "conversations",
    "chat_sessions",
)


def _upgrade_mysql() -> None:
    op.execute(
        """
        CREATE TABLE chat_sessions (
          id          BIGINT       NOT NULL AUTO_INCREMENT,
          user_id     VARCHAR(64)  COLLATE utf8mb4_0900_bin NOT NULL,
          title       VARCHAR(255) NOT NULL,
          persona_id  VARCHAR(64)  COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'tutor',
          subject     VARCHAR(64)  COLLATE utf8mb4_0900_bin NULL,
          created_at  DATETIME(6)  NOT NULL,
          updated_at  DATETIME(6)  NOT NULL,
          PRIMARY KEY (id),
          KEY idx_chat_sessions_user_updated (user_id, updated_at DESC, id DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE conversations (
          id          BIGINT      NOT NULL AUTO_INCREMENT,
          session_id  BIGINT      NULL,
          user_id     VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
          message     MEDIUMTEXT  NOT NULL,
          reply_json  MEDIUMTEXT  NOT NULL,
          created_at  DATETIME(6) NOT NULL,
          PRIMARY KEY (id),
          KEY idx_conversations_session_id (session_id, id DESC),
          KEY idx_conversations_user_id (user_id, id DESC),
          CONSTRAINT fk_conversations_session
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE session_summaries (
          id                    BIGINT      NOT NULL AUTO_INCREMENT,
          session_id            BIGINT      NOT NULL,
          summary_text          MEDIUMTEXT  NOT NULL,
          last_conversation_id  BIGINT      NOT NULL,
          created_at            DATETIME(6) NOT NULL,
          updated_at            DATETIME(6) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_session_summaries_session (session_id),
          KEY idx_session_summaries_last_conversation (last_conversation_id),
          CONSTRAINT fk_session_summaries_session
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE interview_jds (
          id                           BIGINT       NOT NULL AUTO_INCREMENT,
          user_id                      VARCHAR(64)  COLLATE utf8mb4_0900_bin NOT NULL,
          title                        VARCHAR(255) NOT NULL,
          role_family                  VARCHAR(64)  COLLATE utf8mb4_0900_bin NULL,
          seniority                    VARCHAR(32)  COLLATE utf8mb4_0900_bin NULL,
          target_graduation_years_json JSON         NOT NULL,
          raw_text                     MEDIUMTEXT   NOT NULL,
          responsibilities_json        JSON         NOT NULL,
          must_have_json               JSON         NOT NULL,
          core_skills_json             JSON         NOT NULL,
          preferred_skills_json        JSON         NOT NULL,
          bonus_skills_json            JSON         NOT NULL,
          keywords_json                JSON         NOT NULL,
          interview_focus_json         JSON         NOT NULL,
          created_at                   DATETIME(6)  NOT NULL,
          updated_at                   DATETIME(6)  NOT NULL,
          PRIMARY KEY (id),
          KEY idx_interview_jds_user_updated (user_id, updated_at DESC, id DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE public_job_descriptions (
          jd_id              VARCHAR(128)  COLLATE utf8mb4_0900_bin NOT NULL,
          fingerprint        VARCHAR(128)  COLLATE utf8mb4_0900_bin NOT NULL,
          category           VARCHAR(64)   COLLATE utf8mb4_0900_bin NOT NULL,
          source_path        VARCHAR(1024) COLLATE utf8mb4_0900_bin NOT NULL,
          source_path_sha256 CHAR(64)      CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          source_url         VARCHAR(1024) COLLATE utf8mb4_0900_bin NOT NULL,
          title              VARCHAR(255)  NOT NULL,
          company            VARCHAR(255)  NOT NULL,
          salary_raw         VARCHAR(64)   NOT NULL,
          salary_min_k       DECIMAL(8,2)  NOT NULL,
          salary_max_k       DECIMAL(8,2)  NOT NULL,
          education          VARCHAR(32)   NOT NULL,
          recruitment_count  VARCHAR(32)   NOT NULL,
          major              VARCHAR(255)  NOT NULL,
          region             VARCHAR(64)   NOT NULL,
          province           VARCHAR(64)   NOT NULL,
          source_updated_at  VARCHAR(64)   NOT NULL,
          industry           VARCHAR(128)  NOT NULL,
          company_type       VARCHAR(64)   NOT NULL,
          company_size       VARCHAR(64)   NOT NULL,
          relevance          VARCHAR(32)   COLLATE utf8mb4_0900_bin NOT NULL,
          relevance_score    SMALLINT      NOT NULL,
          function_category  VARCHAR(64)   NOT NULL,
          keywords_json      JSON          NOT NULL,
          duplicate_count    INT           NOT NULL,
          row_sha256         CHAR(64)      CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          parent_sha256      CHAR(64)      CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          PRIMARY KEY (jd_id),
          UNIQUE KEY uk_public_jds_source_path_sha256 (source_path_sha256),
          KEY idx_public_jds_filters
            (category, relevance, education, province, salary_min_k, salary_max_k),
          KEY idx_public_jds_fingerprint (fingerprint),
          CONSTRAINT ck_public_jds_duplicate_count CHECK (duplicate_count >= 1)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
          id                CHAR(36)      CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          scope             VARCHAR(16)   COLLATE utf8mb4_0900_bin NOT NULL,
          user_id           VARCHAR(64)   COLLATE utf8mb4_0900_bin NULL,
          session_id        BIGINT        NULL,
          message_id        BIGINT        NULL,
          original_filename VARCHAR(512)  NOT NULL,
          mime_type         VARCHAR(128)  COLLATE utf8mb4_0900_bin NOT NULL,
          size_bytes        BIGINT        NOT NULL,
          storage_path      VARCHAR(1024) COLLATE utf8mb4_0900_bin NOT NULL,
          parsed_path       VARCHAR(1024) COLLATE utf8mb4_0900_bin NULL,
          content_hash      CHAR(64)      CHARACTER SET ascii COLLATE ascii_bin NULL,
          status            VARCHAR(16)   COLLATE utf8mb4_0900_bin NOT NULL,
          parser_name       VARCHAR(64)   COLLATE utf8mb4_0900_bin NULL,
          parser_version    VARCHAR(32)   COLLATE utf8mb4_0900_bin NULL,
          page_count        INT           NULL,
          error_code        VARCHAR(64)   COLLATE utf8mb4_0900_bin NULL,
          error_message     TEXT          NULL,
          created_at        DATETIME(6)   NOT NULL,
          updated_at        DATETIME(6)   NOT NULL,
          expires_at        DATETIME(6)   NULL,
          PRIMARY KEY (id),
          KEY idx_documents_user_session (user_id, session_id),
          KEY idx_documents_status (status),
          KEY idx_documents_expires_at (expires_at),
          CONSTRAINT fk_documents_session
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE RESTRICT,
          CONSTRAINT ck_documents_scope
            CHECK (scope IN ('INTERNAL','PRIVATE','ATTACHMENT')),
          CONSTRAINT ck_documents_status
            CHECK (status IN ('UPLOADED','PARSING','INDEXING','READY',
                              'PARTIAL','FAILED','DELETING','DELETED')),
          CONSTRAINT ck_documents_size CHECK (size_bytes >= 0),
          CONSTRAINT ck_documents_page_count CHECK (page_count IS NULL OR page_count >= 0),
          CONSTRAINT ck_documents_scope_shape CHECK (
               (scope = 'ATTACHMENT' AND user_id IS NOT NULL
                                     AND session_id IS NOT NULL
                                     AND expires_at IS NOT NULL)
            OR (scope = 'PRIVATE'    AND user_id IS NOT NULL AND session_id IS NULL)
            OR (scope = 'INTERNAL'   AND user_id IS NULL AND session_id IS NULL
                                     AND expires_at IS NULL)
          ),
          CONSTRAINT ck_documents_failed_needs_error CHECK (
            status <> 'FAILED'
            OR (error_code IS NOT NULL AND CHAR_LENGTH(TRIM(error_code)) > 0)
          )
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )
    op.execute(
        """
        CREATE TABLE journal_entries (
          id          BIGINT       NOT NULL AUTO_INCREMENT,
          session_id  BIGINT       NULL,
          persona_id  VARCHAR(64)  COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'journal',
          title       VARCHAR(255) NOT NULL,
          content     MEDIUMTEXT   NOT NULL DEFAULT (''),
          tags        VARCHAR(512) NOT NULL DEFAULT '',
          entry_date  DATE         NOT NULL
                      COMMENT '用户本地日历日(date.today())，非 UTC；与 created_at 语义不同，分析时勿混用',
          created_at  DATETIME(6)  NOT NULL,
          updated_at  DATETIME(6)  NOT NULL,
          PRIMARY KEY (id),
          KEY idx_journal_entries_date (entry_date),
          CONSTRAINT fk_journal_entries_session
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC
        """
    )


def _downgrade_mysql() -> None:
    for table in _MYSQL_TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE {table}")


# ---------------------------------------------------------------------------
# SQLite（与阶段 A 验收通过的 schema 等价，保证开发与测试保绿）
# ---------------------------------------------------------------------------

_SQLITE_TABLES_DROP_ORDER = (
    "journal_entries",
    "documents",
    "public_job_descriptions",
    "interview_jds",
    "session_summaries",
    "conversations",
    "chat_sessions",
)


def _upgrade_sqlite() -> None:
    op.execute(
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
    op.execute(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES chat_sessions(id),
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            reply_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE session_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL UNIQUE
                REFERENCES chat_sessions(id) ON DELETE CASCADE,
            summary_text TEXT NOT NULL,
            last_conversation_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE interview_jds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            role_family TEXT,
            seniority TEXT,
            target_graduation_years_json TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            responsibilities_json TEXT NOT NULL,
            must_have_json TEXT NOT NULL,
            core_skills_json TEXT NOT NULL,
            preferred_skills_json TEXT NOT NULL,
            bonus_skills_json TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            interview_focus_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public_job_descriptions (
            jd_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            category TEXT NOT NULL,
            source_path TEXT NOT NULL UNIQUE,
            source_url TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            salary_raw TEXT NOT NULL,
            salary_min_k REAL NOT NULL,
            salary_max_k REAL NOT NULL,
            education TEXT NOT NULL,
            recruitment_count TEXT NOT NULL,
            major TEXT NOT NULL,
            region TEXT NOT NULL,
            province TEXT NOT NULL,
            source_updated_at TEXT NOT NULL,
            industry TEXT NOT NULL,
            company_type TEXT NOT NULL,
            company_size TEXT NOT NULL,
            relevance TEXT NOT NULL,
            relevance_score INTEGER NOT NULL,
            function_category TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            duplicate_count INTEGER NOT NULL CHECK (duplicate_count >= 1),
            row_sha256 TEXT NOT NULL,
            parent_sha256 TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL
                CHECK (scope IN ('INTERNAL', 'PRIVATE', 'ATTACHMENT')),
            user_id TEXT,
            session_id INTEGER
                REFERENCES chat_sessions(id) ON DELETE RESTRICT,
            message_id INTEGER,
            original_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            storage_path TEXT NOT NULL,
            parsed_path TEXT,
            content_hash TEXT,
            status TEXT NOT NULL CHECK (status IN (
                'UPLOADED',
                'PARSING',
                'INDEXING',
                'READY',
                'PARTIAL',
                'FAILED',
                'DELETING',
                'DELETED'
            )),
            parser_name TEXT,
            parser_version TEXT,
            page_count INTEGER CHECK (page_count IS NULL OR page_count >= 0),
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            CHECK (
                (
                    scope = 'ATTACHMENT'
                    AND user_id IS NOT NULL
                    AND session_id IS NOT NULL
                    AND expires_at IS NOT NULL
                )
                OR (
                    scope = 'PRIVATE'
                    AND user_id IS NOT NULL
                    AND session_id IS NULL
                )
                OR (
                    scope = 'INTERNAL'
                    AND user_id IS NULL
                    AND session_id IS NULL
                    AND expires_at IS NULL
                )
            ),
            CHECK (
                status <> 'FAILED'
                OR (error_code IS NOT NULL AND length(trim(error_code)) > 0)
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL,
            persona_id TEXT NOT NULL DEFAULT 'journal',
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            entry_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_chat_sessions_user_updated "
        "ON chat_sessions (user_id, updated_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_conversations_session_id "
        "ON conversations (session_id, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_conversations_user_id "
        "ON conversations (user_id, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_session_summaries_last_conversation "
        "ON session_summaries (last_conversation_id)"
    )
    op.execute(
        "CREATE INDEX idx_interview_jds_user_updated "
        "ON interview_jds (user_id, updated_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_public_jds_filters "
        "ON public_job_descriptions "
        "(category, relevance, education, province, salary_min_k, salary_max_k)"
    )
    op.execute(
        "CREATE INDEX idx_public_jds_fingerprint "
        "ON public_job_descriptions (fingerprint)"
    )
    op.execute(
        "CREATE INDEX idx_documents_user_session "
        "ON documents (user_id, session_id)"
    )
    op.execute(
        "CREATE INDEX idx_documents_status ON documents (status)"
    )
    op.execute(
        "CREATE INDEX idx_documents_expires_at ON documents (expires_at)"
    )
    op.execute(
        "CREATE INDEX idx_journal_entries_date "
        "ON journal_entries (entry_date DESC)"
    )


def _downgrade_sqlite() -> None:
    for table in _SQLITE_TABLES_DROP_ORDER:
        op.execute(f"DROP TABLE {table}")
