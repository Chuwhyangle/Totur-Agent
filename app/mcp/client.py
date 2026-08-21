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
from app.mcp.settings import (
    McpRemoteServerConfig,
    get_mcp_client_retry_seconds,
    get_mcp_client_timeout_seconds,
    load_mcp_client_servers,
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
    if _SENSITIVE_MENTION.search(redacted):
        return "remote call failed (details redacted)"
    return redacted

@dataclass(frozen=True)
class RemoteToolBinding:
    public_name: str
    server: McpRemoteServerConfig
    remote_name: str
    schema: dict[str, Any]

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
    async with httpx.AsyncClient(
        headers=config.headers,
        timeout=timeout_seconds,
        follow_redirects=True,
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
        self.timeout_seconds = timeout_seconds or get_mcp_client_timeout_seconds()
        self.retry_seconds = max(
            retry_seconds if retry_seconds is not None else get_mcp_client_retry_seconds(),
            0.0,
        )
        self._session_factory = session_factory or self._default_session_factory
        self._bindings: dict[str, RemoteToolBinding] = {}
        self.discovery_errors: dict[str, str] = {}
        self.blocked_tools: dict[str, list[str]] = {}
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
        blocked: dict[str, list[str]] = {}
        for server in self.servers:
            try:
                async with self._session_factory(server) as session:
                    cursor: str | None = None
                    while True:
                        result = await session.list_tools(cursor=cursor)
                        for tool in result.tools:
                            if is_write_tool(tool.name, tool.description or ""):
                                blocked.setdefault(server.name, []).append(tool.name)
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
                            bindings[public_name] = RemoteToolBinding(public_name, server, tool.name, schema)
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
