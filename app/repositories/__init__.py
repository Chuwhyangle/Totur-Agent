"""数据库访问层包。

repositories 目录负责放“数据访问代码”。

新手理解：
- route 负责接收 HTTP 请求。
- service 负责业务流程。
- repository 负责读写数据库。

阶段 5 先只会有 conversation_repository.py，
用来保存和查询 Tutor Agent 的对话历史。
"""
