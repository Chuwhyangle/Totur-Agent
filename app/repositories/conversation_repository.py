"""对话历史的数据访问层。

这个文件负责：
1. 把一条用户和 Tutor Agent 的对话保存到 SQLite。
2. 按 user_id 查询某个用户最近的对话历史。
3. 把数据库读写细节藏在 repository 里，避免 route 和 service 到处写 SQL。

这个文件不负责：
1. 接收 HTTP 请求。
2. 调用大模型。
3. 设计 Tutor Agent 的回复内容。

新手理解：
repository 就像“数据库管理员”。
service 不需要知道 SQL 怎么写，只要调用 repository 提供的函数。
"""

from app.db.models import ConversationRecord, CONVERSATIONS_TABLE
from app.db.database import get_connection, initialize_database
from datetime import datetime, timezone

def save_conversation(
    user_id: str,
    message: str,
    reply_json: str,
) -> int:
    """保存一条对话记录，并返回新记录的 id。

    参数说明：
    - user_id: 当前学习者的标识。
    - message: 用户发给 Tutor Agent 的问题。
    - reply_json: Tutor Agent 的结构化回复，已经转换成 JSON 字符串。

    TODO(阶段 5 - 保存对话):
    1. 从 app.db.database 导入 get_connection() 和 initialize_database()。
    2. 调用 initialize_database()，确保 conversations 表已经存在。
    3. 准备 INSERT INTO conversations (...) VALUES (...) SQL。
    4. 写入 user_id、message、reply_json、created_at。
    5. commit 提交数据库修改。
    6. 返回新插入记录的 id。

    下一步我们会先实现这个函数，因为阶段 5 最小闭环是“能保存一条对话”。
    """
    initialize_database()
    insert_sql = f"""
    INSERT INTO {CONVERSATIONS_TABLE} (user_id, message, reply_json, created_at)
    VALUES(?,?,?,?)
    """
    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection()

    try:
        cursor = connection.execute(
            insert_sql,
            (user_id, message, reply_json, created_at),
        )
        connection.commit()
        new_id = cursor.lastrowid

        if new_id is None:
            raise RuntimeError("保存对话失败：没有拿到新记录 id")

        return new_id
    finally:
        connection.close()


def list_recent_conversations(
    user_id: str,
    limit: int = 20,
) -> list[ConversationRecord]:
    """查询某个用户最近的对话历史。

    参数说明：
    - user_id: 要查询哪个学习者的历史。
    - limit: 最多返回多少条，第一版默认 20 条。

    TODO(阶段 5 - 查询历史):
    1. 从 app.db.database 导入 get_connection() 和 initialize_database()。
    2. 调用 initialize_database()，确保 conversations 表已经存在。
    3. 准备 SELECT SQL，按 user_id 过滤。
    4. 按 id 或 created_at 倒序，拿最近 limit 条。
    5. 把 sqlite3.Row 转换成 ConversationRecord。
    6. 返回 ConversationRecord 列表。

    这个函数会在保存逻辑完成后再做。
    """
    initialize_database()
    select_sql = f"""
    SELECT id, user_id, message, reply_json, created_at
    FROM {CONVERSATIONS_TABLE}
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT ?
"""
    connection = get_connection()
    try:
        cursor = connection.execute(
            select_sql,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        conversations = [
            ConversationRecord(
                id=row["id"],
                user_id=row["user_id"],
                message=row["message"],
                reply_json=row["reply_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return conversations
    finally:
        connection.close()
