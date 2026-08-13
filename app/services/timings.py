"""一次请求的分段耗时账本。"""

import threading
import time
from contextlib import contextmanager

_local = threading.local()


def start_request():
    """请求开始时调用，开一本新账。"""
    _local.buckets = {}


def get(name):
    """读某一段的累计毫秒，没有则 None。"""
    return getattr(_local, "buckets", {}).get(name)


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
