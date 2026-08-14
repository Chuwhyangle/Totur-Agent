"""Initialize or upgrade the MySQL Agent observability schema.

Usage: python scripts/init_trace_db.py

The target database is selected by TRACE_DB_NAME.  Business SQLite and Chroma
storage are not touched.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logger = logging.getLogger(__name__)


def main() -> int:
    from app.config import TraceDbConfig
    from app.db.trace_schema import initialize_trace_schema

    config = TraceDbConfig.from_env()
    if not config.enabled:
        logger.error("TRACE_DB_ENABLED=true is required to initialize the trace database")
        return 2

    try:
        import pymysql

        connection = pymysql.connect(**config.connection_kwargs)
    except Exception as exc:
        logger.error("trace database connection failed error_type=%s", type(exc).__name__)
        return 1

    try:
        initialize_trace_schema(connection)
    except Exception as exc:
        logger.error("trace database schema initialization failed error_type=%s", type(exc).__name__)
        return 1
    finally:
        connection.close()

    logger.info("trace database schema is ready database=%s", config.name)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
