"""Agent 埋点数据写入 MySQL。"""

import os

from dotenv import load_dotenv
import pymysql

_DB_CONFIG: dict | None = None

INSERT_TRACE_SQL = """
INSERT INTO agent_traces
    (trace_id, user_id, session_id, persona_id, model,
     question, total_ms, retrieval_ms, llm_ms, status,
     react_rounds, llm_calls, tool_calls, tool_failures,
     embed_ms, search_ms, rerank_ms, tool_other_ms,
     prompt_tokens, completion_tokens)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_RETRIEVAL_EVENT_SQL = """
INSERT INTO retrieval_events
    (trace_id, query, collection,
     embed_ms, search_ms, rerank_ms, cost_ms,
     top_k, candidate_count, hit_count, top_score, min_score, passed,
     threshold, rerank_applied, rerank_fallback, corpus_fingerprint)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_LLM_CALL_SQL = """
INSERT INTO llm_calls
    (trace_id, round_number, call_type, model,
     prompt_tokens, completion_tokens, total_tokens, cost_ms, finish_reason)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_TOOL_CALL_SQL = """
INSERT INTO tool_calls
    (trace_id, round_number, tool_name, channel, forced, ok, error_code, cost_ms, args_preview)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def load_db_config() -> dict:
    """从环境变量读取 MySQL 连接配置，缺少必填项时抛错。"""
    global _DB_CONFIG

    if _DB_CONFIG is None:
        load_dotenv()
        required = {
            "user": os.getenv("TRACE_DB_USER", "").strip(),
            "password": os.getenv("TRACE_DB_PASSWORD", "").strip(),
            "database": os.getenv("TRACE_DB_NAME", "").strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"缺少 TRACE_DB_* 配置: {', '.join(missing)}")
        _DB_CONFIG = {
            "host": os.getenv("TRACE_DB_HOST", "127.0.0.1").strip(),
            "port": int(os.getenv("TRACE_DB_PORT", "3306")),
            **required,
            "charset": "utf8mb4",
        }

    return dict(_DB_CONFIG)


def save_trace(
    user_id,
    question,
    total_ms,
    retrieval_ms=None,
    llm_ms=None,
    status="OK",
    trace_id=None,
    session_id=None,
    persona_id=None,
    model=None,
    react_rounds=None,
    llm_calls=None,
    tool_calls=None,
    tool_failures=None,
    embed_ms=None,
    search_ms=None,
    rerank_ms=None,
    tool_other_ms=None,
    prompt_tokens=None,
    completion_tokens=None,
):
    """记录一次 agent 请求。写失败也不影响主流程。"""
    try:
        conn = pymysql.connect(**load_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_TRACE_SQL,
                    (
                        trace_id,
                        user_id,
                        session_id,
                        persona_id,
                        model,
                        question,
                        total_ms,
                        retrieval_ms,
                        llm_ms,
                        status,
                        react_rounds,
                        llm_calls,
                        tool_calls,
                        tool_failures,
                        embed_ms,
                        search_ms,
                        rerank_ms,
                        tool_other_ms,
                        prompt_tokens,
                        completion_tokens,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[trace] 埋点写入失败，已忽略: {exc}")


def save_retrieval_event(
    *,
    trace_id,
    query,
    collection,
    embed_ms=None,
    search_ms=None,
    rerank_ms=None,
    cost_ms=None,
    top_k=None,
    candidate_count=None,
    hit_count=None,
    top_score=None,
    min_score=None,
    passed=None,
    threshold=None,
    rerank_applied=None,
    rerank_fallback=None,
    corpus_fingerprint=None,
):
    """记录一次检索。写失败也不影响主流程；没有 trace_id 时跳过。"""
    if not trace_id:
        return
    try:
        conn = pymysql.connect(**load_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_RETRIEVAL_EVENT_SQL,
                    (
                        trace_id,
                        query,
                        collection,
                        embed_ms,
                        search_ms,
                        rerank_ms,
                        cost_ms,
                        top_k,
                        candidate_count,
                        hit_count,
                        top_score,
                        min_score,
                        passed,
                        threshold,
                        rerank_applied,
                        rerank_fallback,
                        corpus_fingerprint,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[trace] 检索事件写入失败，已忽略: {exc}")


def save_llm_call(
    *,
    trace_id,
    round_number=None,
    call_type=None,
    model=None,
    prompt_tokens=None,
    completion_tokens=None,
    total_tokens=None,
    cost_ms=None,
    finish_reason=None,
):
    """记录一次 LLM 调用。写失败也不影响主流程；没有 trace_id 时跳过。"""
    if not trace_id:
        return
    try:
        conn = pymysql.connect(**load_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_LLM_CALL_SQL,
                    (
                        trace_id,
                        round_number,
                        call_type,
                        model,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cost_ms,
                        finish_reason,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[trace] LLM 调用写入失败，已忽略: {exc}")


def save_tool_call(
    *,
    trace_id,
    round_number=None,
    tool_name=None,
    channel=None,
    forced=None,
    ok=None,
    error_code=None,
    cost_ms=None,
    args_preview=None,
):
    """记录一次工具调用。写失败也不影响主流程；没有 trace_id 时跳过。"""
    if not trace_id:
        return
    try:
        conn = pymysql.connect(**load_db_config())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_TOOL_CALL_SQL,
                    (
                        trace_id,
                        round_number,
                        tool_name,
                        channel,
                        forced,
                        ok,
                        error_code,
                        cost_ms,
                        args_preview,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[trace] 工具调用写入失败，已忽略: {exc}")
