"""Execute Tutor Agent tool calls with structured error handling."""

from __future__ import annotations

import json
import time
from typing import Any

from app.db.trace_db import save_tool_call
from app.services import timings
from app.services.agent.tools.registry import ToolRegistry
from app.services.tool_metrics import observe_tool_call

RAG_TOOL_NAME = "search_learning_notes"


class ToolExecutor:
    """Runs registered tools from a model-requested name and arguments."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        default_tool_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.default_tool_kwargs = {
            name: dict(kwargs) for name, kwargs in (default_tool_kwargs or {}).items()
        }

    def set_default_tool_kwargs(self, default_tool_kwargs: dict[str, dict[str, Any]]) -> None:
        """Replace request-scoped defaults before executing a tool round."""

        self.default_tool_kwargs = {
            name: dict(kwargs) for name, kwargs in default_tool_kwargs.items()
        }

    def execute(self, name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
        """Execute one tool call and always return a structured result."""

        tool = self.registry.get_tool(name)
        if tool is None:
            self._record_tool_call(
                name,
                arguments,
                ok=False,
                error_code="tool_not_found",
                cost_ms=0,
            )
            return {
                "ok": False,
                "error": "tool_not_found",
                "message": f"unknown tool: {name}",
            }

        parsed_arguments = self._parse_arguments(arguments)
        if parsed_arguments is None:
            self._record_tool_call(
                name,
                arguments,
                ok=False,
                error_code="invalid_arguments",
                cost_ms=0,
            )
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": "tool arguments must be a JSON object.",
            }

        merged_arguments = dict(self.default_tool_kwargs.get(name, {}))
        merged_arguments.update(parsed_arguments)

        bucket = "retrieval" if name == RAG_TOOL_NAME else "tool_other"
        started_at = time.perf_counter()

        try:
            with timings.track(bucket):
                if self._is_external_tool(name):
                    result = tool(**merged_arguments)
                    self._record_tool_call(
                        name,
                        merged_arguments,
                        ok=_result_ok(result),
                        error_code=None,
                        cost_ms=int((time.perf_counter() - started_at) * 1000),
                    )
                    return result
                with observe_tool_call(name, "internal") as metric:
                    result = tool(**merged_arguments)
                    metric.set_ok(_result_ok(result))
                    self._record_tool_call(
                        name,
                        merged_arguments,
                        ok=_result_ok(result),
                        error_code=None,
                        cost_ms=int((time.perf_counter() - started_at) * 1000),
                    )
                    return result
        except TypeError as exc:
            self._record_tool_call(
                name,
                merged_arguments,
                ok=False,
                error_code="invalid_arguments",
                cost_ms=int((time.perf_counter() - started_at) * 1000),
            )
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": f"invalid tool arguments: {exc}",
            }
        except Exception as exc:  # pragma: no cover - defensive boundary.
            self._record_tool_call(
                name,
                merged_arguments,
                ok=False,
                error_code="tool_execution_failed",
                cost_ms=int((time.perf_counter() - started_at) * 1000),
            )
            return {
                "ok": False,
                "error": "tool_execution_failed",
                "message": f"tool execution failed: {exc}",
            }

    def _record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any] | str,
        *,
        ok: bool,
        error_code: str | None,
        cost_ms: int,
    ) -> None:
        """记录一次工具调用到 tool_calls，并维护请求级计数。

        五个返回路径都要经过这里，保证 agent_traces.tool_calls 汇总
        与 tool_calls 表行数一致。所有失败也会 bump tool_failures。
        """

        try:
            preview = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            preview = str(arguments)
        if preview is None:
            preview = None
        else:
            preview = preview[:500]

        timings.bump("tool_calls")
        if not ok:
            timings.bump("tool_failures")

        save_tool_call(
            trace_id=timings.get_trace_id(),
            round_number=timings.get_meta("round_number"),
            tool_name=name,
            channel="mcp" if self._is_external_tool(name) else "internal",
            forced=int(bool(timings.get_meta("forced"))),
            ok=int(ok),
            error_code=error_code,
            cost_ms=cost_ms,
            args_preview=preview,
        )

    def _is_external_tool(self, name: str) -> bool:
        checker = getattr(self.registry, "is_external_tool", None)
        if checker is None:
            return False
        try:
            return bool(checker(name))
        except Exception:
            return False

    def _parse_arguments(self, arguments: dict[str, Any] | str) -> dict[str, Any] | None:
        if isinstance(arguments, dict):
            return arguments

        if not isinstance(arguments, str):
            return None

        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        return parsed


def _result_ok(result: Any) -> bool:
    """工具返回 dict 时看 ok 字段；非 dict（MCP 等）视为成功。"""
    return bool(result.get("ok")) if isinstance(result, dict) else True
