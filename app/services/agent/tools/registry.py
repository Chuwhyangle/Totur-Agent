"""Registry for Tutor Agent callable tools."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.services.agent.tools.save_journal_entry import save_journal_entry
from app.services.agent.tools.search_attachments import search_attachments
from app.services.agent.tools.search_job_descriptions import search_job_descriptions
from app.services.agent.tools.search_learning_notes import search_learning_notes
from app.services.agent.tools.score_jd_skill_fit import score_jd_skill_fit
from app.services.agent.tools.web_search import web_search
from app.services import rag_settings

logger = logging.getLogger(__name__)


def _sanitize_exception(exc: BaseException) -> str:
    """Redact MCP-related exception text without a hard dependency on app.mcp.

    Falls back to a type-only message when the MCP client module cannot be
    imported, so registry.py still loads when the optional MCP stack is
    absent and never forwards raw exception text that might embed secrets.
    """
    try:
        from app.mcp.client import sanitize_error_message
    except ImportError:
        return f"{type(exc).__name__} (details redacted)"
    return sanitize_error_message(str(exc))


SEARCH_ATTACHMENTS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_attachments",
        "description": (
            "Search documents the user uploaded in the current conversation "
            "(resumes, PDFs, learning materials). Use it when the question "
            "references an uploaded file. Do NOT use for notes (use "
            "search_learning_notes), public JDs (use search_job_descriptions), "
            "or current events (use web_search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The question or topic to search within the uploaded "
                        "documents."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of evidence chunks to return.",
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
            "study notes, previous plans, retrospectives, and architecture "
            "notes. Use for what the user has studied or built, or internal "
            "project facts. Do NOT use for job market questions (use "
            "search_job_descriptions), uploaded files (use search_attachments), "
            "or current/external events (use web_search)."
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
                "subject": {
                    "type": ["string", "null"],
                    "description": (
                        "Subject shard to search; omit to use the current session subject. "
                        "Leave null for cross-subject broadcast retrieval."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


SEARCH_JOB_DESCRIPTIONS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_job_descriptions",
        "description": (
            "Search the indexed public job-description corpus by meaning and "
            "optional structured filters, then return complete source JDs. "
            "Use for job market questions: responsibilities, skill requirements, "
            "salary ranges, education requirements, or interview focus from "
            "public postings. Do NOT use for the user's own notes (use "
            "search_learning_notes), uploaded files (use search_attachments), "
            "or current events (use web_search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Role, responsibility, skill, or job requirement to search.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                },
                "direction": {
                    "type": ["string", "null"],
                    "enum": ["agent_dev", "marketing", None],
                },
                "relevance": {
                    "type": ["string", "null"],
                    "enum": ["直接相关", "较相关", "相邻岗位", None],
                },
                "education": {
                    "type": ["string", "null"],
                    "description": "Exact normalized education requirement.",
                },
                "province": {
                    "type": ["string", "null"],
                    "description": "Normalized province, municipality, or 全国.",
                },
                "salary_floor_k": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "description": "Require the advertised lower bound to be at least this k/month.",
                },
                "salary_ceiling_k": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "description": "Require the advertised upper bound to be at most this k/month.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search public web sources for current or external information. "
            "Use it for recent changes, current versions, news, policies, "
            "prices, schedules, or facts unavailable in local notes or JDs. "
            "Do NOT use for the user's own notes (use search_learning_notes), "
            "public job postings (use search_job_descriptions), or uploaded "
            "files (use search_attachments)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A concise standalone query without chat history, "
                        "secrets, or private user data."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 5,
                },
                "freshness_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3650,
                    "description": (
                        "Optional recency window in days. Omit when recency "
                        "is not required."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


SAVE_JOURNAL_ENTRY_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "save_journal_entry",
        "description": (
            "Save a daily journal/diary entry recording what the user learned, "
            "accomplished, or reflected on today. Content should be in markdown format."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A concise title for the journal entry.",
                },
                "content": {
                    "type": "string",
                    "description": "The journal entry content in markdown format.",
                },
                "tags": {
                    "type": "string",
                    "description": (
                        "Comma-separated tags for categorization, e.g. 'FastAPI,学习,项目进展'."
                    ),
                },
                "entry_date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Defaults to today if omitted.",
                },
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
    },
}


class ToolRegistry:
    """Keeps tool schemas and Python callables in one small boundary."""

    def __init__(self, mcp_client_adapter: Any | None = None) -> None:
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "save_journal_entry": save_journal_entry,
            "search_attachments": search_attachments,
            "search_job_descriptions": search_job_descriptions,
            "search_learning_notes": search_learning_notes,
            "score_jd_skill_fit": score_jd_skill_fit,
            "web_search": web_search,
        }
        self._mcp_client_adapter = mcp_client_adapter
        if self._mcp_client_adapter is None:
            try:
                from app.mcp.settings import is_mcp_client_enabled

                if is_mcp_client_enabled():
                    from app.mcp.client import MCPClientAdapter

                    self._mcp_client_adapter = MCPClientAdapter()
            except Exception as exc:
                # Settings errors never include secret values; client errors
                # are sanitized before logging. Redact defensively anyway so
                # no raw MCP exception text (which could embed config) leaks.
                logger.warning(
                    "MCP client unavailable, continuing with local tools only: %s",
                    _sanitize_exception(exc),
                )
                self._mcp_client_adapter = None

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas."""

        learning_notes_schema = deepcopy(SEARCH_LEARNING_NOTES_SCHEMA)
        if not rag_settings.ENABLE_SUBJECT_SHARDING:
            # Preserve the legacy tool contract while the feature flag is off.
            learning_notes_schema["function"]["parameters"]["properties"].pop(
                "subject", None
            )

        schemas = [
            learning_notes_schema,
            deepcopy(SEARCH_JOB_DESCRIPTIONS_SCHEMA),
            deepcopy(SEARCH_ATTACHMENTS_SCHEMA),
            deepcopy(SCORE_JD_SKILL_FIT_SCHEMA),
            deepcopy(SAVE_JOURNAL_ENTRY_SCHEMA),
            deepcopy(WEB_SEARCH_SCHEMA),
        ]
        if self._mcp_client_adapter is not None:
            try:
                schemas.extend(self._mcp_client_adapter.get_tools_schema())
            except Exception as exc:
                # Never fail the whole tool list because MCP schema discovery
                # broke: log a redacted warning and keep local tools working.
                logger.warning(
                    "MCP tool schema unavailable, continuing with local tools only: %s",
                    _sanitize_exception(exc),
                )
        return schemas

    def has_tool(self, name: str) -> bool:
        """Check whether a tool is registered."""

        if name in self._tools:
            return True
        return self.is_external_tool(name)

    def is_external_tool(self, name: str) -> bool:
        """Check whether a tool is provided by an external MCP server."""

        if self._mcp_client_adapter is None:
            return False
        try:
            return bool(self._mcp_client_adapter.has_tool(name))
        except Exception as exc:
            # Do not swallow silently; log a redacted warning and degrade to
            # "not an external tool" so local tool resolution still works.
            logger.warning(
                "MCP tool availability check failed for %s: %s",
                name,
                _sanitize_exception(exc),
            )
            return False

    def get_tool(self, name: str) -> Callable[..., dict[str, Any]] | None:
        """Return a registered tool callable by name."""

        local_tool = self._tools.get(name)
        if local_tool is not None:
            return local_tool
        if self.is_external_tool(name):
            return lambda **kwargs: self._mcp_client_adapter.execute(name, kwargs)
        return None
