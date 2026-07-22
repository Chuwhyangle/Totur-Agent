"""Execute Tutor Agent tool calls with structured error handling."""

from __future__ import annotations

import json
from typing import Any

from app.services.agent.tools.registry import ToolRegistry
from app.services.tool_metrics import observe_tool_call


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
            return {
                "ok": False,
                "error": "tool_not_found",
                "message": f"unknown tool: {name}",
            }

        parsed_arguments = self._parse_arguments(arguments)
        if parsed_arguments is None:
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": "tool arguments must be a JSON object.",
            }

        merged_arguments = dict(self.default_tool_kwargs.get(name, {}))
        merged_arguments.update(parsed_arguments)

        try:
            if self._is_external_tool(name):
                return tool(**merged_arguments)
            with observe_tool_call(name, "internal") as metric:
                result = tool(**merged_arguments)
                metric.set_ok(bool(result.get("ok")) if isinstance(result, dict) else True)
                return result
        except TypeError as exc:
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": f"invalid tool arguments: {exc}",
            }
        except Exception as exc:  # pragma: no cover - defensive boundary.
            return {
                "ok": False,
                "error": "tool_execution_failed",
                "message": f"tool execution failed: {exc}",
            }

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
