"""Tests for external MCP client tool adaptation."""
from __future__ import annotations
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio

from app.mcp import client as mcp_client
from app.mcp.client import MCPClientAdapter
from app.mcp.settings import McpRemoteServerConfig
from app.services.agent.tools.registry import ToolRegistry


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    async def list_tools(self, cursor=None):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="echo",
                    description="Echo arguments",
                    inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                )
            ],
            nextCursor=None,
        )

    async def call_tool(self, name, arguments):
        return SimpleNamespace(isError=False, structuredContent={"ok": True, "echo": arguments}, content=[])


def test_mcp_client_adapter_discovers_and_calls_remote_tool():
    server = McpRemoteServerConfig(name="demo", transport="stdio", command="demo")
    adapter = MCPClientAdapter(servers=[server], session_factory=lambda _: FakeSessionContext(FakeSession()))

    schemas = adapter.get_tools_schema()
    assert schemas[0]["function"]["name"] == "mcp_demo_echo"

    result = adapter.execute("mcp_demo_echo", {"text": "hello"})
    assert result["ok"] is True
    assert result["echo"] == {"text": "hello"}


def test_streamable_http_client_follows_endpoint_redirects(monkeypatch):
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeClientSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def initialize(self):
            return None

    @asynccontextmanager
    async def fake_streamable_http_client(url, *, http_client):
        yield object(), object(), lambda: None

    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(mcp_client, "ClientSession", FakeClientSession)
    monkeypatch.setattr(mcp_client, "streamable_http_client", fake_streamable_http_client)

    config = McpRemoteServerConfig(
        name="demo-http",
        transport="streamable-http",
        url="http://example.test/mcp",
    )

    async def exercise() -> None:
        async with mcp_client._connect_server(config, timeout_seconds=1):
            pass

    anyio.run(exercise)
    assert captured["follow_redirects"] is True


def test_tool_registry_merges_external_mcp_schemas_and_execution():
    class Adapter:
        def get_tools_schema(self):
            return [{"type": "function", "function": {"name": "mcp_demo_echo", "description": "Echo", "parameters": {"type": "object", "properties": {}}}}]

        def has_tool(self, name):
            return name == "mcp_demo_echo"

        def execute(self, name, arguments):
            return {"ok": True, "name": name, "arguments": arguments}

    registry = ToolRegistry(mcp_client_adapter=Adapter())
    names = [schema["function"]["name"] for schema in registry.get_tools_schema()]
    assert "mcp_demo_echo" in names
    assert registry.has_tool("mcp_demo_echo") is True
    assert registry.get_tool("mcp_demo_echo")(text="hello")["arguments"] == {"text": "hello"}
