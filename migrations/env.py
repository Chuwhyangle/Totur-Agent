"""Alembic 迁移环境。

复用 app.db.engine.get_engine() 的单例引擎，保证 Alembic 与应用
始终操作同一个数据库；不引入 ORM metadata，SQL 全部手写在迁移文件里。
"""

from __future__ import annotations

from alembic import context

from app.db.engine import get_engine

# 无 ORM 模型，target_metadata 保持 None。
target_metadata = None


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 而不执行（--sql）。"""

    context.configure(
        url=get_engine().url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接在应用引擎的连接上执行迁移。"""

    engine = get_engine()
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
