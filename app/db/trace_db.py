"""Agent 埋点数据写入 MySQL。"""

import os

from dotenv import load_dotenv
import pymysql

INSERT_TRACE_SQL = """
INSERT INTO agent_traces
    (user_id, question, total_ms, retrieval_ms, llm_ms, status)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def load_db_config() -> dict:
    """从环境变量读取 MySQL 连接配置，缺少必填项时抛错。"""
    load_dotenv()
    required = {
        "user": os.getenv("TRACE_DB_USER", "").strip(),
        "password": os.getenv("TRACE_DB_PASSWORD", "").strip(),
        "database": os.getenv("TRACE_DB_NAME", "").strip(),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"缺少 TRACE_DB_* 配置: {', '.join(missing)}")
    return {
        "host": os.getenv("TRACE_DB_HOST", "127.0.0.1").strip(),
        "port": int(os.getenv("TRACE_DB_PORT", "3306")),
        **required,
        "charset": "utf8mb4",
    }


def save_trace(
    user_id,
    question,
    total_ms,
    retrieval_ms=None,
    llm_ms=None,
    status="OK",
):
    """记录一次 agent 请求。写失败也不影响主流程。"""
    try:
        conn = pymysql.connect(**load_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_TRACE_SQL,
                    (user_id, question, total_ms, retrieval_ms, llm_ms, status),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[trace] 埋点写入失败，已忽略: {exc}")
