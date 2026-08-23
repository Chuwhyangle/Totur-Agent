"""conversations.reply_format: 历史回复格式版本化

存量行默认 json_v1（旧五字段 JSON），新写入标记 markdown_v2（Markdown 正文）。
读取时按此列显式分发 parser，禁止对内容做格式嗅探。

Revision ID: 0002_conversations_reply_format
Revises: 0001_initial
Create Date: 2026-08-19

"""

from alembic import op

revision = "0002_conversations_reply_format"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _is_mysql(bind) -> bool:
    return bind.dialect.name == "mysql"


def upgrade() -> None:
    bind = op.get_bind()
    if _is_mysql(bind):
        op.execute(
            "ALTER TABLE conversations "
            "ADD COLUMN reply_format VARCHAR(32) CHARACTER SET ascii "
            "COLLATE ascii_bin NOT NULL DEFAULT 'json_v1' "
            "AFTER reply_json"
        )
    else:
        op.execute(
            "ALTER TABLE conversations "
            "ADD COLUMN reply_format TEXT NOT NULL DEFAULT 'json_v1'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _is_mysql(bind):
        op.execute("ALTER TABLE conversations DROP COLUMN reply_format")
    else:
        # SQLite 不支持 DROP COLUMN 的旧版本兜底：重建表。
        op.execute(
            "ALTER TABLE conversations "
            "DROP COLUMN reply_format"
        )
