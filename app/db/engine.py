"""SQLAlchemy Engine 单例：全应用的数据库连接入口。

阶段 A 只连 SQLite；URL 由 StorageConfig 惰性求值，割接时换成
mysql+pymysql:// 即可，repositories 层无需改动。
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from app.config import StorageConfig


_engine: Engine | None = None


def _build_database_url() -> str:
    """从环境配置读取当前数据库连接串（每次调用都重新读 env，方便测试隔离）。"""

    return StorageConfig.from_env().database_url


def _configure_sqlite_connection(dbapi_connection, _record) -> None:
    """每个 SQLite 底层连接只执行一次：外键检查必须逐连接开启。"""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 5000")
    finally:
        cursor.close()


def get_engine() -> Engine:
    """返回进程级单例 Engine；首次调用时按当前配置创建。"""

    global _engine
    if _engine is None:
        url = _build_database_url()
        kwargs: dict = dict(
            pool_pre_ping=True,
            connect_args={"timeout": 5.0},
        )
        if url.startswith("mysql"):
            kwargs.update(
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,  # 必须 < MySQL wait_timeout(默认 28800)
                pool_timeout=10,
                connect_args={"init_command": "SET time_zone = '+00:00'"},
            )
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _configure_sqlite_connection)
    return _engine


def reset_engine_for_tests() -> None:
    """测试隔离：释放当前 Engine，下次 get_engine() 按新配置重建。"""

    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
