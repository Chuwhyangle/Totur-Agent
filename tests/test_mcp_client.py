"""Tests for external MCP client tool adaptation."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from threading import Barrier, Lock
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


class EmptySession:
    async def list_tools(self, cursor=None):
        return SimpleNamespace(tools=[], nextCursor=None)


def test_mcp_client_adapter_discovers_and_calls_remote_tool():
    server = McpRemoteServerConfig(name="demo", transport="stdio", command="demo")
    adapter = MCPClientAdapter(servers=[server], session_factory=lambda _: FakeSessionContext(FakeSession()))

    schemas = adapter.get_tools_schema()
    assert schemas[0]["function"]["name"] == "mcp_demo_echo"

    result = adapter.execute("mcp_demo_echo", {"text": "hello"})
    assert result["ok"] is True
    assert result["echo"] == {"text": "hello"}


def test_empty_tool_discovery_is_not_repeated():
    server = McpRemoteServerConfig(name="empty", transport="stdio", command="empty")
    discovery_count = 0

    def session_factory(_):
        nonlocal discovery_count
        discovery_count += 1
        return FakeSessionContext(EmptySession())

    adapter = MCPClientAdapter(servers=[server], session_factory=session_factory)

    assert adapter.get_tools_schema() == []
    assert adapter.get_tools_schema() == []
    assert discovery_count == 1


def test_partial_discovery_failure_is_retried_after_retry_interval():
    healthy = McpRemoteServerConfig(name="healthy", transport="stdio", command="healthy")
    recovering = McpRemoteServerConfig(name="recovering", transport="stdio", command="recovering")
    discovery_counts = {"healthy": 0, "recovering": 0}

    def session_factory(server):
        discovery_counts[server.name] += 1
        if server.name == "recovering" and discovery_counts[server.name] == 1:
            raise RuntimeError("temporarily unavailable")
        return FakeSessionContext(FakeSession())

    adapter = MCPClientAdapter(
        servers=[healthy, recovering],
        session_factory=session_factory,
        retry_seconds=0,
    )

    first_names = {schema["function"]["name"] for schema in adapter.get_tools_schema()}
    assert first_names == {"mcp_healthy_echo"}
    assert "recovering" in adapter.discovery_errors

    second_names = {schema["function"]["name"] for schema in adapter.get_tools_schema()}
    assert second_names == {"mcp_healthy_echo", "mcp_recovering_echo"}
    assert adapter.discovery_errors == {}
    assert discovery_counts["recovering"] == 2


def test_concurrent_schema_requests_share_one_discovery():
    server = McpRemoteServerConfig(name="empty", transport="stdio", command="empty")
    worker_count = 6
    barrier = Barrier(worker_count)
    counter_lock = Lock()
    discovery_count = 0

    class SlowEmptySession:
        async def list_tools(self, cursor=None):
            await anyio.sleep(0.05)
            return SimpleNamespace(tools=[], nextCursor=None)

    def session_factory(_):
        nonlocal discovery_count
        with counter_lock:
            discovery_count += 1
        return FakeSessionContext(SlowEmptySession())

    adapter = MCPClientAdapter(servers=[server], session_factory=session_factory)

    def get_schemas():
        barrier.wait()
        return adapter.get_tools_schema()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(lambda _: get_schemas(), range(worker_count)))

    assert results == [[]] * worker_count
    assert discovery_count == 1


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
