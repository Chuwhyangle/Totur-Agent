"""MCP client adapter that exposes remote tools to the local ReAct loop."""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from threading import Lock, Thread
from typing import Any, AsyncContextManager, Callable
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from app.mcp.github_policy import (
    BLOCK_REASON_NOT_IN_ALLOWLIST,
    BLOCK_REASON_WRITE_GUARD,
    is_github_server,
)
from app.mcp.settings import (
    McpRemoteServerConfig,
    get_mcp_client_retry_seconds,
    get_mcp_client_timeout_seconds,
    load_mcp_client_servers,
    validate_github_server_config,
)
from app.mcp.write_guard import is_write_tool
from app.services.tool_metrics import observe_tool_call

logger = logging.getLogger(__name__)
SessionFactory = Callable[[McpRemoteServerConfig], AsyncContextManager[ClientSession]]

_BEARER_TOKEN = re.compile(r"(?i)(bearer)\s+[^\s,;\"'<>]+")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|proxy-authorization|x-api-key|api[-_]?key|"
    r"access[-_]?token|auth[-_]?token|password|passwd|secret)\b"
    r"(\s*[:=]\s*)[^\s,;\"'\)]+"
)
_SENSITIVE_MENTION = re.compile(
    r"(?i)\b(authorization|proxy-authorization|x-api-key|api[-_]?key|"
    r"password|passwd|secret|bearer|access[-_]?token|auth[-_]?token)\b"
)
# Bare GitHub token formats: redacted even when the error text mentions no
# Authorization/Bearer keyword at all. Kept as two explicit patterns:
# - fine-grained PATs (github_pat_) may contain underscores;
# - classic/OAuth tokens (ghp_/gho_/ghu_/ghs_/ghr_) are alphanumeric runs.
# The character class must consume the whole token so no tail is left behind.
_FINE_GRAINED_GITHUB_TOKEN = re.compile(r"(?i)\bgithub[_-]?pat_[A-Za-z0-9_]+")
_CLASSIC_GITHUB_TOKEN = re.compile(r"(?i)\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]+")


def sanitize_error_message(text: str) -> str:
    """Redact secrets from error text before it reaches logs or users.

    Never prints Authorization headers, tokens, passwords, or PAT values.
    When a sensitive key is still mentioned after redaction, fall back to a
    generic message instead of risking partial leakage.
    """
    if not text:
        return text
    redacted = _BEARER_TOKEN.sub(r"\1 <redacted>", text)
    redacted = _SENSITIVE_ASSIGNMENT.sub(r"\1\2<redacted>", redacted)
    redacted = _FINE_GRAINED_GITHUB_TOKEN.sub("<redacted>", redacted)
    redacted = _CLASSIC_GITHUB_TOKEN.sub("<redacted>", redacted)
    if _SENSITIVE_MENTION.search(redacted):
        return "remote call failed (details redacted)"
    return redacted

@dataclass(frozen=True)
class RemoteToolBinding:
    public_name: str
    server: McpRemoteServerConfig
    remote_name: str
    schema: dict[str, Any]
    remote_description: str = ""

@asynccontextmanager
async def _connect_server(config: McpRemoteServerConfig, timeout_seconds: float):
    timeout = timedelta(seconds=timeout_seconds)
    if config.transport == "stdio":
        environment = dict(os.environ)
        environment.update(config.env or {})
        parameters = StdioServerParameters(command=config.command or "", args=list(config.args), env=environment, cwd=config.cwd)
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=timeout) as session:
                await session.initialize()
                yield session
        return
    # GitHub hosted MCP never follows redirects: a redirect to a different
    # scheme/host/port must not receive the Authorization header. The
    # canonical URL validated at config load is used directly. Non-GitHub
    # servers keep the legacy redirect behavior.
    follow_redirects = not is_github_server(config.name, config.url)
    async with httpx.AsyncClient(
        headers=config.headers,
        timeout=timeout_seconds,
        follow_redirects=follow_redirects,
    ) as http_client:
        async with streamable_http_client(config.url or "", http_client=http_client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=timeout) as session:
                await session.initialize()
                yield session

class MCPClientAdapter:
    """Discover and execute external MCP tools with structured degradation."""
    def __init__(
        self,
        servers: list[McpRemoteServerConfig] | None = None,
        session_factory: SessionFactory | None = None,
        timeout_seconds: float | None = None,
        retry_seconds: float | None = None,
    ) -> None:
        self.servers = list(servers if servers is not None else load_mcp_client_servers())
        # Hand-built McpRemoteServerConfig instances bypass the config loader,
        # so re-run the same lightweight GitHub security validation here
        # (shared helpers in settings.py; non-GitHub servers pass through).
        for server in self.servers:
            validate_github_server_config(server, prefix=f"MCP server {server.name!r}")
        self.timeout_seconds = timeout_seconds or get_mcp_client_timeout_seconds()
        self.retry_seconds = max(
            retry_seconds if retry_seconds is not None else get_mcp_client_retry_seconds(),
            0.0,
        )
        self._session_factory = session_factory or self._default_session_factory
        self._bindings: dict[str, RemoteToolBinding] = {}
        self.discovery_errors: dict[str, str] = {}
        # Server name -> list of {"name": tool, "reason": ...} entries.
        # Only tool names and security reasons are recorded, never arguments,
        # headers, or tokens.
        self.blocked_tools: dict[str, list[dict[str, str]]] = {}
        self._discovery_attempted = False
        self._next_retry_at = 0.0
        self._discovery_lock = Lock()

    def _default_session_factory(self, config: McpRemoteServerConfig) -> AsyncContextManager[ClientSession]:
        return _connect_server(config, self.timeout_seconds)

    def refresh(self) -> list[dict[str, Any]]:
        return self._refresh_if_needed(force=True)

    def get_tools_schema(self) -> list[dict[str, Any]]:
        return self._refresh_if_needed(force=False)

    def _refresh_if_needed(self, *, force: bool) -> list[dict[str, Any]]:
        with self._discovery_lock:
            now = time.monotonic()
            should_refresh = force or (
                bool(self.servers)
                and (
                    not self._discovery_attempted
                    or (bool(self.discovery_errors) and now >= self._next_retry_at)
                )
            )
            if should_refresh:
                _run_async(self._discover())
                self._discovery_attempted = True
                self._next_retry_at = time.monotonic() + self.retry_seconds
            return [binding.schema for binding in self._bindings.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._bindings

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        binding = self._bindings.get(name)
        if binding is None:
            return {"ok": False, "error": "tool_not_found", "message": f"unknown MCP tool: {name}"}
        # Re-check the server policy right before any remote call, so even a
        # caller that bypasses the registry/discovery path can never trigger
        # a remote request for a blocked tool.
        reason = _tool_block_reason(
            binding.server, binding.remote_name, binding.remote_description
        )
        if reason is not None:
            logger.warning("MCP tool %s blocked before execution: %s", name, reason)
            return {
                "ok": False,
                "error": "mcp_tool_blocked",
                "message": f"MCP tool {binding.remote_name} is blocked by the server policy",
                "server": binding.server.name,
                "tool": binding.remote_name,
            }
        with observe_tool_call(name, "mcp_client") as metric:
            try:
                result = _run_async(self._call(binding, arguments))
            except Exception as exc:
                safe_message = sanitize_error_message(str(exc))
                logger.warning("MCP tool %s failed: %s", name, safe_message)
                metric.set_ok(False)
                return {"ok": False, "error": "mcp_tool_failed", "message": safe_message, "server": binding.server.name, "tool": binding.remote_name}
            metric.set_ok(bool(result.get("ok")))
            return result

    async def _discover(self) -> list[dict[str, Any]]:
        bindings: dict[str, RemoteToolBinding] = {}
        errors: dict[str, str] = {}
        blocked: dict[str, list[dict[str, str]]] = {}
        for server in self.servers:
            try:
                async with self._session_factory(server) as session:
                    cursor: str | None = None
                    while True:
                        result = await session.list_tools(cursor=cursor)
                        for tool in result.tools:
                            # Defense order: server allowlist first (primary
                            # boundary), write_guard second (defense in depth).
                            reason = _tool_block_reason(
                                server, tool.name, tool.description or ""
                            )
                            if reason is not None:
                                blocked.setdefault(server.name, []).append(
                                    {"name": tool.name, "reason": reason}
                                )
                                continue
                            public_name = _public_tool_name(server.name, tool.name, set(bindings))
                            description = f"[{server.name} MCP] {tool.description or tool.name}"
                            schema = {
                                "type": "function",
                                "function": {
                                    "name": public_name,
                                    "description": description,
                                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                                },
                            }
                            bindings[public_name] = RemoteToolBinding(
                                public_name, server, tool.name, schema,
                                remote_description=tool.description or "",
                            )
                        cursor = getattr(result, "nextCursor", None)
                        if not cursor:
                            break
            except Exception as exc:
                safe_message = sanitize_error_message(str(exc))
                errors[server.name] = safe_message
                logger.warning("MCP server discovery failed for %s: %s", server.name, safe_message)
        self._bindings = bindings
        self.discovery_errors = errors
        self.blocked_tools = blocked
        return [binding.schema for binding in bindings.values()]

    async def _call(self, binding: RemoteToolBinding, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self._session_factory(binding.server) as session:
            response = await session.call_tool(binding.remote_name, arguments)
        structured = getattr(response, "structuredContent", None)
        is_error = bool(getattr(response, "isError", False))
        texts = [getattr(item, "text", "") for item in response.content if getattr(item, "type", None) == "text"]
        message = "\n".join(text for text in texts if text)
        if is_error:
            return {"ok": False, "error": "mcp_remote_error", "message": sanitize_error_message(message or "remote MCP tool failed"), "server": binding.server.name, "tool": binding.remote_name}
        if isinstance(structured, dict):
            result = dict(structured)
            result.setdefault("ok", True)
            result.setdefault("mcp_server", binding.server.name)
            return result
        return {"ok": True, "content": message, "mcp_server": binding.server.name, "tool": binding.remote_name}

def _tool_block_reason(
    config: McpRemoteServerConfig, tool_name: str, description: str = ""
) -> str | None:
    """Return the security reason a remote tool must be blocked, or None.

    Defense order:
    1. The server-level allowed_tools allowlist is the primary boundary.
       GitHub configs always carry a non-empty allowlist (validated at load
       time); a GitHub config without one fails closed and blocks everything.
    2. write_guard is only the second layer for obvious write tools.

    Non-GitHub servers without an allowlist keep the legacy behavior: only
    write_guard applies, exactly as before this policy existed.
    """
    allowed = config.allowed_tools
    if allowed:
        if tool_name not in allowed:
            return BLOCK_REASON_NOT_IN_ALLOWLIST
    elif is_github_server(config.name, config.url):
        # GitHub without an explicit allowlist: fail closed, block all.
        return BLOCK_REASON_NOT_IN_ALLOWLIST
    if is_write_tool(tool_name, description):
        return BLOCK_REASON_WRITE_GUARD
    return None


def _public_tool_name(server_name: str, tool_name: str, existing: set[str]) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"mcp_{server_name}_{tool_name}").strip("_")
    candidate = normalized[:64] or "mcp_tool"
    if candidate not in existing:
        return candidate
    digest = hashlib.sha256(f"{server_name}:{tool_name}".encode()).hexdigest()[:8]
    return f"{candidate[:55]}_{digest}"

def _run_async(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    result: list[Any] = []
    error: list[BaseException] = []
    def runner() -> None:
        try:
            result.append(asyncio.run(awaitable))
        except BaseException as exc:
            error.append(exc)
    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
