"""Registry for Tutor Agent callable tools."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.services.agent.tools.interview_jd_search import search_interview_jds
from app.services.agent.tools.search_learning_notes import search_learning_notes
from app.services.agent.tools.score_jd_skill_fit import score_jd_skill_fit


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


SCORE_JD_SKILL_FIT_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "score_jd_skill_fit",
        "description": (
            "Calculate a weighted JD skill fit score from LLM-provided "
            "per-skill judgments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_role": {
                    "type": "string",
                    "description": "The target role or JD direction being scored.",
                },
                "skills": {
                    "type": "array",
                    "description": (
                        "Per-skill judgments prepared by the model from the JD "
                        "and the user's self-reported skills."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Skill name, such as RAG or FastAPI.",
                            },
                            "jd_importance": {
                                "type": "integer",
                                "description": "How important this skill is to the JD.",
                                "minimum": 1,
                                "maximum": 5,
                            },
                            "user_level": {
                                "type": "integer",
                                "description": "User's current mastery level.",
                                "minimum": 0,
                                "maximum": 5,
                            },
                            "confidence": {
                                "type": "string",
                                "description": "Confidence in this judgment.",
                                "enum": ["low", "medium", "high"],
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Evidence from user notes or project history.",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for the score.",
                            },
                            "recommended_action": {
                                "type": "string",
                                "description": "Suggested next action for this skill.",
                            },
                        },
                        "required": ["name", "jd_importance", "user_level"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                },
            },
            "required": ["skills"],
            "additionalProperties": False,
        },
    },
}


SEARCH_LEARNING_NOTES_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_learning_notes",
        "description": (
            "Search the user's own indexed learning notes for project docs, "
            "study notes, previous plans, retrospectives, and architecture notes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The concept, previous note, plan, or learning material "
                        "to search for."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of note chunks to return.",
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
            "search_learning_notes": search_learning_notes,
            "score_jd_skill_fit": score_jd_skill_fit,
        }

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas."""

        return [
            deepcopy(INTERVIEW_JD_SEARCH_SCHEMA),
            deepcopy(SEARCH_LEARNING_NOTES_SCHEMA),
            deepcopy(SCORE_JD_SKILL_FIT_SCHEMA),
        ]

    def has_tool(self, name: str) -> bool:
        """Check whether a tool is registered."""

        return name in self._tools

    def get_tool(self, name: str) -> Callable[..., dict[str, Any]] | None:
        """Return a registered tool callable by name."""

        return self._tools.get(name)
