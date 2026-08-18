"""业务库 schema 生命周期。

B2 起由 Alembic 接管：initialize_database() 只负责把库升级到 head，
所有 DDL 位于 migrations/versions/ 下，此处不再保留任何 DDL 字符串。
"""

from pathlib import Path

from alembic import command
from alembic.config import Config


def initialize_database() -> None:
    """把业务库 schema 升级到 Alembic head（幂等；已是最新则 no-op）。"""

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    command.upgrade(config, "head")
