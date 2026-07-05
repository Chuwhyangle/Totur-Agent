"""Registry for Tutor Agent callable tools."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.services.agent.tools.interview_jd_search import search_interview_jds


INTERVIEW_JD_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "interview_jd_search",
        "description": (
            "Search saved technical interview job descriptions for "
            "responsibilities, skills, keywords, interview focus, and excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The role direction, technical topic, or interview intent "
                        "to search for."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of JD results to return.",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


class ToolRegistry:
    """Keeps tool schemas and Python callables in one small boundary."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "interview_jd_search": search_interview_jds,
        }

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas."""

        return [deepcopy(INTERVIEW_JD_SEARCH_SCHEMA)]

    def has_tool(self, name: str) -> bool:
        """Check whether a tool is registered."""

        return name in self._tools

    def get_tool(self, name: str) -> Callable[..., dict[str, Any]] | None:
        """Return a registered tool callable by name."""

        return self._tools.get(name)
