"""一次请求的分段耗时账本。"""

import threading
import time
import uuid
from contextlib import contextmanager

_local = threading.local()


def start_request(trace_id: str | None = None) -> str:
    """请求开始时调用，开一本新账，并生成这次请求的 trace_id。

    返回 trace_id，调用方可以直接落库。
    """
    trace_id = trace_id or uuid.uuid4().hex
    _local.buckets = {}
    _local.counters = {}
    _local.meta = {"trace_id": trace_id}
    return trace_id


def get_trace_id():
    """返回当前请求的 trace_id，没有则 None。"""
    return get_meta("trace_id")


def get(name):
    """读某一段的累计毫秒，没有则 None。"""
    return getattr(_local, "buckets", {}).get(name)


def count(name):
    """读某个计数，没有则 None。"""
    return getattr(_local, "counters", {}).get(name)


def set_meta(key, value):
    """写入请求级标量（trace_id、model 等）。"""
    meta = getattr(_local, "meta", None)
    if meta is not None:
        meta[key] = value


def get_meta(key):
    """读请求级标量，没有则 None。"""
    return getattr(_local, "meta", {}).get(key)


@contextmanager
def track(name):
    """用 with 包住一段代码，自动计时并累加。"""
    start = time.perf_counter()
    try:
        yield
    finally:
        cost = int((time.perf_counter() - start) * 1000)
        buckets = getattr(_local, "buckets", None)
        if buckets is not None:
            buckets[name] = buckets.get(name, 0) + cost


def bump(name, n: int = 1):
    """计数器累加（react_rounds / llm_calls / tool_calls / token 数）。"""
    counters = getattr(_local, "counters", None)
    if counters is not None:
        counters[name] = counters.get(name, 0) + n


def bump_ms(name, ms: int | float):
    """把已经测好的毫秒数累加进某个耗时桶，不再重新计时。"""
    if ms is None:
        return
    buckets = getattr(_local, "buckets", None)
    if buckets is not None:
        buckets[name] = buckets.get(name, 0) + int(ms)
