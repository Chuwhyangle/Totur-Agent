"""SQLite 数据库连接与初始化。

这个文件负责：
1. 定义数据库文件保存在哪里。
2. 创建 SQLite 连接。
3. 后续提供初始化数据库表的函数。


新手理解：
你可以把这个文件理解成“数据库入口”。以后其他模块想读写 SQLite，
应该优先通过这里拿到连接，而不是到处自己写连接代码。
"""

from pathlib import Path
import sqlite3

from app.db.models import CONVERSATIONS_TABLE


# 项目根目录：当前文件在 app/db/database.py，所以 parents[2] 是项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# SQLite 数据库文件路径。
# 后续运行项目时，如果这个文件不存在，SQLite 可以自动创建它。
DATABASE_PATH = PROJECT_ROOT / "tutor_agent.db"


def get_connection() -> sqlite3.Connection:
    """创建并返回一个 SQLite 数据库连接。

    当前阶段先只做最小连接能力。
    后面 repository 会调用这个函数来保存和查询对话历史。
    """

    connection = sqlite3.connect(DATABASE_PATH)

    # 让查询结果可以像字典一样按字段名读取，例如 row["user_id"]。
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database() -> None:
    """初始化数据库。

    这个函数会创建 conversations 表。
    `IF NOT EXISTS` 的意思是：如果表已经存在，就不要重复创建，也不要报错。
    """

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {CONVERSATIONS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        reply_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """

    connection = get_connection()
    try:
        connection.execute(create_table_sql)
        connection.commit()
    finally:
        connection.close()
