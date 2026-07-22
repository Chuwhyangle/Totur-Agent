"""Tutor Agent MCP server with stdio and Streamable HTTP transports."""
from __future__ import annotations
import logging
from typing import Any
from starlette.types import ASGIApp, Receive, Scope, Send
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import NotificationOptions
from app.mcp import prompts, resources, tools
from app.mcp.settings import get_mcp_auth_token, is_mcp_server_enabled
from app.services import rag_settings

logger = logging.getLogger(__name__)

class _BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.token and scope.get("type") == "http":
            headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
            authorization = headers.get("authorization", "")
            if authorization != f"Bearer {self.token}":
                from starlette.responses import JSONResponse
                await JSONResponse({"detail": "MCP bearer token required"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)

class TutorMCP(FastMCP):
    def __init__(self) -> None:
        self._dynamic_shard_tools: set[str] = set()
        self._resource_signature = resources.manifest_state_signature()
        super().__init__(
            name="Tutor Agent",
            instructions="检索学习笔记、分析面试 JD、生成带来源测验，并提供项目资源。",
            streamable_http_path="/",
            json_response=True,
            stateless_http=False,
        )
        original_create = self._mcp_server.create_initialization_options
        def create_initialization_options(notification_options=None, experimental_capabilities=None):
            return original_create(
                notification_options or NotificationOptions(prompts_changed=True, resources_changed=True, tools_changed=True),
                experimental_capabilities or {},
            )
        self._mcp_server.create_initialization_options = create_initialization_options

    async def list_tools(self):
        if self._refresh_dynamic_shard_tools():
            await self._notify("tools")
        return await super().list_tools()

    async def list_resources(self):
        if self._refresh_resource_signature():
            await self._notify("resources")
        return await super().list_resources()

    def _refresh_dynamic_shard_tools(self) -> bool:
        if not rag_settings.ENABLE_SUBJECT_SHARDING:
            return False
        manifest_dir = resources._project_root() / rag_settings.CHROMA_PERSIST_DIR
        current_slugs = {path.stem.removeprefix("index_manifest_") for path in manifest_dir.glob("index_manifest_*.json")}
        current_slugs = {slug for slug in current_slugs if slug}
        expected = {f"search_notes_{slug}" for slug in current_slugs}
        changed = expected != self._dynamic_shard_tools
        for name in self._dynamic_shard_tools - expected:
            try:
                self.remove_tool(name)
            except Exception:
                logger.debug("dynamic MCP tool already absent: %s", name)
        for slug in sorted(current_slugs - {name.removeprefix("search_notes_") for name in self._dynamic_shard_tools}):
            name = f"search_notes_{slug}"
            self.add_tool(
                _make_subject_search_tool(slug),
                name=name,
                description=f"Search the {slug} learning-note shard.",
            )
        self._dynamic_shard_tools = expected
        return changed

    def _refresh_resource_signature(self) -> bool:
        current = resources.manifest_state_signature()
        if current == self._resource_signature:
            return False
        self._resource_signature = current
        return True

    async def _notify(self, kind: str) -> None:
        try:
            session = self._mcp_server.request_context.session
            if kind == "tools":
                await session.send_tool_list_changed()
            else:
                await session.send_resource_list_changed()
        except LookupError:
            pass


def _make_subject_search_tool(slug: str):
    def search_subject_notes(query: str, limit: int = 3) -> dict[str, Any]:
        return tools.tool_search_learning_notes(query=query, limit=limit, subject=slug)

    search_subject_notes.__name__ = f"search_notes_{slug}"
    return search_subject_notes

mcp = TutorMCP()

@mcp.tool(name="search_learning_notes")
def search_learning_notes(query: str, limit: int = 3, subject: str | None = None) -> dict[str, Any]:
    """Search the local learning-note RAG index and return source-linked excerpts."""
    return tools.tool_search_learning_notes(query=query, limit=limit, subject=subject)

@mcp.tool(name="interview_jd_search")
def interview_jd_search(query: str, limit: int = 3) -> dict[str, Any]:
    """Search saved interview job descriptions."""
    return tools.tool_interview_jd_search(query=query, limit=limit)

@mcp.tool(name="score_jd_skill_fit")
def score_jd_skill_fit(skills: list[dict[str, Any]], target_role: str | None = None) -> dict[str, Any]:
    """Calculate a weighted fit score from per-skill judgments."""
    return tools.tool_score_jd_skill_fit(skills=skills, target_role=target_role)

@mcp.tool(name="generate_quiz")
def generate_quiz(query: str, count: int = 3, subject: str | None = None) -> dict[str, Any]:
    """Generate source-linked practice questions from local learning notes."""
    return tools.tool_generate_quiz(query=query, count=count, subject=subject)

@mcp.resource("manifest://index", name="index_manifest", mime_type="application/json")
def index_manifest() -> str:
    return resources.json_resource(resources.manifest_resource_payload())

@mcp.resource("docs://catalog", name="docs_catalog", mime_type="application/json")
def docs_catalog() -> str:
    return resources.json_resource(resources.docs_catalog_payload())

@mcp.resource("reports://catalog", name="reports_catalog", mime_type="application/json")
def reports_catalog() -> str:
    return resources.json_resource(resources.reports_catalog_payload())

@mcp.resource("metrics://tools", name="tool_metrics", mime_type="application/json")
def tool_metrics() -> str:
    return resources.json_resource(resources.metrics_resource_payload())

@mcp.resource("docs://content/{path}", name="doc_content", mime_type="text/markdown")
def doc_content(path: str) -> str:
    return resources.read_project_file("docs", path)

@mcp.resource("reports://content/{path}", name="report_content", mime_type="text/plain")
def report_content(path: str) -> str:
    return resources.read_project_file("reports", path)

@mcp.prompt(name="tutor")
def tutor_prompt() -> str:
    return prompts.render_persona_prompt("tutor")

@mcp.prompt(name="algorithm_coach")
def algorithm_coach_prompt() -> str:
    return prompts.render_persona_prompt("algorithm_coach")

@mcp.prompt(name="interviewer")
def interviewer_prompt() -> str:
    return prompts.render_persona_prompt("interviewer")

@mcp.prompt(name="quiz")
def quiz_prompt(topic: str = "当前学习主题", count: int = 3) -> str:
    return prompts.render_quiz_prompt(topic=topic, count=count)

@mcp.prompt(name="interview")
def interview_prompt(target_role: str = "目标技术岗位") -> str:
    return prompts.render_interview_prompt(target_role=target_role)

_http_app = None

def get_mcp_http_app():
    global _http_app
    if _http_app is None:
        _http_app = _BearerAuthMiddleware(mcp.streamable_http_app(), get_mcp_auth_token())
    return _http_app

def get_mcp_http_lifespan():
    return mcp.session_manager.run()

def run_stdio() -> None:
    if not is_mcp_server_enabled():
        raise SystemExit("MCP_SERVER_ENABLED=true is required to run the MCP server")
    mcp.run(transport="stdio")
