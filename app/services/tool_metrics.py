"""In-process tool latency metrics for internal and MCP channels."""
from __future__ import annotations
from collections import defaultdict, deque
from contextlib import AbstractContextManager
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Any

@dataclass(frozen=True)
class ToolMetric:
    name: str
    channel: str
    latency_ms: float
    ok: bool

_METRICS: deque[ToolMetric] = deque(maxlen=2000)
_LOCK = Lock()

class ToolCallObservation(AbstractContextManager["ToolCallObservation"]):
    def __init__(self, name: str, channel: str) -> None:
        self.name = name
        self.channel = channel
        self.ok = False
        self.started_at = 0.0
    def __enter__(self) -> "ToolCallObservation":
        self.started_at = perf_counter()
        return self
    def set_ok(self, ok: bool) -> None:
        self.ok = ok
    def __exit__(self, exc_type, exc, traceback) -> bool:
        latency_ms = (perf_counter() - self.started_at) * 1000
        with _LOCK:
            _METRICS.append(ToolMetric(self.name, self.channel, latency_ms, self.ok and exc_type is None))
        return False

def observe_tool_call(name: str, channel: str) -> ToolCallObservation:
    return ToolCallObservation(name=name, channel=channel)

def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)

def tool_metrics_snapshot() -> dict[str, Any]:
    with _LOCK:
        metrics = list(_METRICS)
    grouped: dict[tuple[str, str], list[ToolMetric]] = defaultdict(list)
    for metric in metrics:
        grouped[(metric.channel, metric.name)].append(metric)
    groups = []
    for (channel, name), items in sorted(grouped.items()):
        latencies = [item.latency_ms for item in items]
        groups.append({
            "channel": channel,
            "name": name,
            "calls": len(items),
            "failures": sum(1 for item in items if not item.ok),
            "p50_ms": _percentile(latencies, 0.50),
            "p95_ms": _percentile(latencies, 0.95),
        })
    return {"ok": True, "sample_size": len(metrics), "groups": groups}

def reset_tool_metrics() -> None:
    with _LOCK:
        _METRICS.clear()
