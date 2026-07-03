"""数据库数据模型说明。

这个文件负责：
1. 描述数据库里要保存哪些数据。
2. 记录 conversations 表的字段含义。
3. 后续可以放 Python 数据结构，帮助代码更清楚地表达“一条对话记录”。

新手理解：
database.py 更像“怎么连接数据库”；
models.py 更像“数据库里要保存什么样的数据”。
"""

from dataclasses import dataclass


# conversations 是阶段 5 的核心表，用来保存每一次用户和 Agent 的对话。
CONVERSATIONS_TABLE = "conversations"


@dataclass
class ConversationRecord:
    """一条对话历史记录。

    这个类对应 conversations 表里的一行数据。

    字段说明：
    - id: 每条记录的唯一编号，也就是主键。
    - user_id: 区分不同学习者的字符串，第一版先不用登录系统。
    - message: 用户发给 Tutor Agent 的原始问题。
    - reply_json: Tutor Agent 返回的结构化回复，保存成 JSON 字符串。
    - created_at: 这条对话记录创建的时间。

    TODO(阶段 5 - 数据模型):
    1. 确认这些字段是否足够支撑第一版对话历史。
    2. 后续 repository 查询 SQLite 后，可以把查询结果转换成这个类。
    3. 如果未来增加学习进度、任务状态，不要直接塞进这张表，应该另建表。
    """

    id: int
    user_id: str
    message: str
    reply_json: str
    created_at: str


# TODO(阶段 5 - 表结构):
# conversations 表计划包含以下字段：
#
# id INTEGER PRIMARY KEY AUTOINCREMENT
# user_id TEXT NOT NULL
# message TEXT NOT NULL
# reply_json TEXT NOT NULL
# created_at TEXT NOT NULL
#
# 下一步会在 database.py 的 initialize_database() 里把这个设计写成 CREATE TABLE SQL。
