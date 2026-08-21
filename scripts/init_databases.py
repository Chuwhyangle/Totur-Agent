"""Initialize business databases on MySQL (idempotent).

Usage:
    python scripts/init_databases.py

Creates the two databases of the one-instance-two-database design
(数据库重构文档 D1) and the separated application/analyst grants (B4):

    tutor_agent     business data (7 tables, via Alembic)
    tutor_agent_ops observability traces

Required env (see .env.example):
    TRACE_DB_HOST / TRACE_DB_PORT   MySQL server coordinates
    MYSQL_ROOT_PASSWORD             root password for DDL/grants
    MYSQL_APP_PASSWORD              password for the 'app' user
    MYSQL_ANALYST_PASSWORD          password for the 'analyst' user
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logger = logging.getLogger(__name__)

CREATE_DATABASE_SQL = """
CREATE DATABASE IF NOT EXISTS {name}
  DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_0900_ai_ci
"""


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()

    host = os.getenv("TRACE_DB_HOST", "127.0.0.1")
    port = int(os.getenv("TRACE_DB_PORT", "3306"))
    root_password = os.getenv("MYSQL_ROOT_PASSWORD", "")
    app_password = os.getenv("MYSQL_APP_PASSWORD", "")
    analyst_password = os.getenv("MYSQL_ANALYST_PASSWORD", "")

    if not root_password:
        logger.error("MYSQL_ROOT_PASSWORD is required")
        return 1

    connection = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=root_password,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            for name in ("tutor_agent", "tutor_agent_ops"):
                cursor.execute(CREATE_DATABASE_SQL.format(name=name))
                logger.info("database ensured: %s", name)

            if app_password:
                cursor.execute(
                    "CREATE USER IF NOT EXISTS 'app'@'%%' "
                    "IDENTIFIED BY %s",
                    (app_password,),
                )
            if analyst_password:
                cursor.execute(
                    "CREATE USER IF NOT EXISTS 'analyst'@'%%' "
                    "IDENTIFIED BY %s",
                    (analyst_password,),
                )

            # 权限分离（数据库重构文档 §3.B4）。空 tuple 触发 mogrify
            # 把 %% 还原为 %（pymysql 无参 execute 不做 %-格式化）。
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON tutor_agent.* TO 'app'@'%%'",
                (),
            )
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE "
                "ON tutor_agent_ops.* TO 'app'@'%%'",
                (),
            )
            cursor.execute(
                "GRANT SELECT ON tutor_agent.* TO 'analyst'@'%%'",
                (),
            )
            cursor.execute(
                "GRANT SELECT ON tutor_agent_ops.* TO 'analyst'@'%%'",
                (),
            )
            logger.info("users/grants ensured: app, analyst")
    finally:
        connection.close()

    # 迁移由 root 执行（DDL 权限）；应用账号按 B4 只有 DML 权限，
    # 启动时对已迁移库的 upgrade 为 no-op（只需读 alembic_version）。
    _run_migrations(host, port, root_password)

    logger.info("done")
    return 0


def _run_migrations(host: str, port: int, root_password: str) -> None:
    """用 root 账号执行 Alembic upgrade head。"""

    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = (
        f"mysql+pymysql://root:{root_password}@{host}:{port}/tutor_agent"
    )
    from app.db.engine import reset_engine_for_tests

    reset_engine_for_tests()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(config, "head")
    logger.info("alembic upgrade head done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
