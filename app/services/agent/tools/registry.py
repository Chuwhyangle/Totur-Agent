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
from app.services.agent.tools.update_learning_progress import (
    SCHEMA as UPDATE_LEARNING_PROGRESS_SCHEMA,
    TOOL_NAME as UPDATE_LEARNING_PROGRESS_TOOL_NAME,
    update_learning_progress,
)
from app.services.agent.tools.web_search import web_search
from app.services.agent.tools.create_markdown_artifact import (
    SCHEMA as CREATE_MARKDOWN_ARTIFACT_SCHEMA,
    create_markdown_artifact,
)
from app.services.agent.tools.list_workspace_assets import (
    SCHEMA as LIST_WORKSPACE_ASSETS_SCHEMA,
    list_workspace_assets,
)
from app.services.agent.tools.read_workspace_asset import (
    SCHEMA as READ_WORKSPACE_ASSET_SCHEMA,
    read_workspace_asset,
)
from app.services.agent.tools.search_workspace_assets import (
    SCHEMA as SEARCH_WORKSPACE_ASSETS_SCHEMA,
    search_workspace_assets,
)
from app.services import rag_settings

logger = logging.getLogger(__name__)

WORKSPACE_TOOL_SCHEMAS = {
    "list_workspace_assets": LIST_WORKSPACE_ASSETS_SCHEMA,
    "read_workspace_asset": READ_WORKSPACE_ASSET_SCHEMA,
    "search_workspace_assets": SEARCH_WORKSPACE_ASSETS_SCHEMA,
    "create_markdown_artifact": CREATE_MARKDOWN_ARTIFACT_SCHEMA,
}
WORKSPACE_TOOL_NAMES = frozenset(WORKSPACE_TOOL_SCHEMAS)


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
            "accomplished, or reflected on today. Content should be in markdown format. "
            "Do NOT use this tool to update structured SQL learning progress; "
            "use update_learning_progress when the user explicitly requests a progress update."
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
            UPDATE_LEARNING_PROGRESS_TOOL_NAME: update_learning_progress,
            "web_search": web_search,
            "list_workspace_assets": list_workspace_assets,
            "read_workspace_asset": read_workspace_asset,
            "search_workspace_assets": search_workspace_assets,
            "create_markdown_artifact": create_markdown_artifact,
        }
        self._mcp_client_adapter = mcp_client_adapter
        if self._mcp_client_adapter is None:
            try:
                from app.mcp.settings import is_mcp_client_enabled

                if is_mcp_client_enabled():
                    from app.mcp.client import MCPClientAdapter

                    self._mcp_client_adapter = MCPClientAdapter()
            except Exception as exc:
                # Config errors from app.mcp.settings never include secret
                # values; client errors are sanitized before logging.
                logger.warning(
                    "MCP client unavailable, continuing with local tools only: %s",
                    exc,
                )
                self._mcp_client_adapter = None

    def get_tools_schema(self, execution_context=None) -> list[dict[str, Any]]:
        """Return tools allowed for the current request mode."""

        if (
            execution_context is not None
            and getattr(execution_context, "progress_update_requested", False)
        ):
            # Progress mode is deliberately isolated: the model must not turn
            # a structured progress update into a journal entry or retrieval.
            return [deepcopy(UPDATE_LEARNING_PROGRESS_SCHEMA)]

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
            except Exception:
                pass
        if execution_context is not None and self.workspace_context_error(execution_context) is None:
            schemas.extend(deepcopy(schema) for schema in WORKSPACE_TOOL_SCHEMAS.values())
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
        except Exception:
            return False

    def is_workspace_tool(self, name: str) -> bool:
        return name in WORKSPACE_TOOL_NAMES

    def requires_execution_context(self, name: str) -> bool:
        return self.is_workspace_tool(name) or name == UPDATE_LEARNING_PROGRESS_TOOL_NAME

    def workspace_context_error(
        self,
        execution_context,
        name: str | None = None,
    ) -> str | None:
        """Return a stable rejection code before a context-bound tool can run."""

        if name == UPDATE_LEARNING_PROGRESS_TOOL_NAME:
            if execution_context is None:
                return "execution_context_required"
            if not getattr(execution_context, "progress_update_requested", False):
                return "progress_update_not_requested"
            return None
        if name is not None and not self.is_workspace_tool(name):
            return None
        if execution_context is None or execution_context.workspace_id is None:
            return "workspace_context_required"
        from app.services.workspaces.settings import is_workspaces_enabled
        from app.services.workspaces.workspace_service import (
            WorkspaceArchivedError,
            WorkspaceNotFoundError,
            WorkspaceService,
        )

        if not is_workspaces_enabled():
            return "workspace_disabled"
        try:
            WorkspaceService().require_active_owned_workspace(
                user_id=execution_context.user_id,
                workspace_id=execution_context.workspace_id,
            )
        except WorkspaceArchivedError:
            return "workspace_archived"
        except WorkspaceNotFoundError:
            return "workspace_context_required"
        return None

    def get_tool(self, name: str, execution_context=None) -> Callable[..., dict[str, Any]] | None:
        """Return a registered tool callable by name."""

        local_tool = self._tools.get(name)
        if local_tool is not None:
            return local_tool
        if self.is_external_tool(name):
            return lambda **kwargs: self._mcp_client_adapter.execute(name, kwargs)
        return None
