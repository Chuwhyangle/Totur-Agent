"""业务库 schema 生命周期。

B2 起由 Alembic 接管：initialize_database() 只负责把库升级到 head，
所有 DDL 位于 migrations/versions/ 下，此处不再保留任何 DDL 字符串。

存量库兼容：Alembic 接管之前由旧 DDL 创建的库没有 alembic_version 表。
如果库里已有业务表但没有任何版本记录，先 stamp 0001_initial 再增量升级，
避免迁移 0001 重建已存在的表导致启动失败。
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.engine import get_engine
from app.db.models import CONVERSATIONS_TABLE


def initialize_database() -> None:
    """把业务库 schema 升级到 Alembic head（幂等；已是最新则 no-op）。"""

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    _stamp_pre_alembic_database(config)
    command.upgrade(config, "head")


def _stamp_pre_alembic_database(config: Config) -> None:
    """存量库没有版本记录但已有业务表时，按 0001 打点。

    只看 alembic_version 表是否存在不够：失败的升级会留下空版本表。
    以版本行数为准——没有行就说明迁移从未成功过。
    """

    if not _table_exists(CONVERSATIONS_TABLE):
        # 全新库：保持从 0001 开始建表的正常路径。
        return
    if _alembic_version_count() > 0:
        return
    command.stamp(config, "0001_initial")


def _alembic_version_count() -> int:
    """返回 alembic_version 表中的版本行数；表不存在时为 0。"""

    if not _table_exists("alembic_version"):
        return 0

    engine = get_engine()
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT COUNT(*) AS total FROM alembic_version"),
        ).mappings().fetchone()

    return int(row["total"])


def _table_exists(table_name: str) -> bool:
    """判断当前业务库中是否存在某张表（方言无关的轻量探测）。"""

    engine = get_engine()
    if engine.dialect.name == "mysql":
        query = text(
            "SELECT COUNT(*) AS total FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :table_name"
        )
    else:
        query = text(
            "SELECT COUNT(*) AS total FROM sqlite_master "
            "WHERE type = 'table' AND name = :table_name"
        )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {"table_name": table_name},
        ).mappings().fetchone()

    return int(row["total"]) > 0
