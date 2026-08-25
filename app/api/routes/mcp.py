"""Public, credential-free status for configured MCP integrations."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter

from app.mcp.client import MCPClientAdapter
from app.mcp.settings import (
    GITHUB_MCP_HOST,
    get_github_mcp_projects,
    is_mcp_client_enabled,
    load_mcp_client_servers,
)


router = APIRouter(prefix="/mcp", tags=["mcp"])


def _is_github_server(server) -> bool:
    host = ""
    if server.url:
        try:
            host = (urlparse(server.url).hostname or "").lower()
        except ValueError:
            host = ""
    return server.name.lower() == "github" or host == GITHUB_MCP_HOST


def _project_payload(full_name: str) -> dict[str, str]:
    owner, name = full_name.split("/", 1)
    return {
        "full_name": full_name,
        "owner": owner,
        "name": name,
        "url": f"https://github.com/{full_name}",
    }


@router.get("/github/status")
def github_mcp_status() -> dict:
    """Return safe MCP connection state, tools, and declared repositories.

    The response deliberately omits headers, token values, and raw server
    configuration. Repository names come from ``GITHUB_MCP_PROJECTS`` rather
    than attempting to infer a PAT's private selection through GitHub APIs.
    """

    projects = [_project_payload(item) for item in get_github_mcp_projects()]
    payload = {
        "provider": "GitHub Hosted MCP",
        "enabled": False,
        "status": "disabled",
        "readonly": True,
        "server_name": None,
        "transport": None,
        "projects": projects,
        "tool_count": 0,
        "tools": [],
        "blocked_write_tool_count": 0,
        "error": None,
    }

    if not is_mcp_client_enabled():
        return payload

    payload["enabled"] = True
    try:
        servers = [server for server in load_mcp_client_servers() if _is_github_server(server)]
    except RuntimeError as exc:
        payload.update(status="configuration_error", error=str(exc))
        return payload

    if not servers:
        payload.update(status="not_configured", error="No GitHub MCP server is configured.")
        return payload

    server = servers[0]
    payload.update(
        server_name=server.name,
        transport=server.transport,
    )
    adapter = MCPClientAdapter(servers=servers)
    schemas = adapter.refresh()
    payload["tools"] = [schema["function"]["name"] for schema in schemas]
    payload["tool_count"] = len(payload["tools"])
    payload["blocked_write_tool_count"] = sum(
        len(names) for names in adapter.blocked_tools.values()
    )

    if adapter.discovery_errors:
        payload["status"] = "degraded" if schemas else "unavailable"
        payload["error"] = next(iter(adapter.discovery_errors.values()))
    else:
        payload["status"] = "connected" if schemas else "empty"
    return payload

