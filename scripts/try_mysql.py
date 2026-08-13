"""练手脚本：手动向 agent_traces 插一条埋点，验证 MySQL 写入。

运行：.venv/Scripts/python.exe scripts/try_mysql.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymysql

from app.db.trace_db import INSERT_TRACE_SQL, load_db_config

conn = pymysql.connect(**load_db_config())
try:
    with conn.cursor() as cur:
        cur.execute(
            INSERT_TRACE_SQL,
            ("wenhao", "Python插进来的", 2000, 150, 1700, "OK"),
        )
    conn.commit()
    print("插入成功")
finally:
    conn.close()
