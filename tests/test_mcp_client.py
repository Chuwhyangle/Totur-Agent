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
from app.mcp.write_guard import is_write_tool
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
        headers={
            "Authorization": "Bearer test-placeholder",
            "X-MCP-Readonly": "true",
            "X-MCP-Toolsets": "repos,issues,pull_requests",
        },
    )

    async def exercise() -> None:
        async with mcp_client._connect_server(config, timeout_seconds=1):
            pass

    anyio.run(exercise)
    assert captured["follow_redirects"] is True
    assert captured["headers"] == {
        "Authorization": "Bearer test-placeholder",
        "X-MCP-Readonly": "true",
        "X-MCP-Toolsets": "repos,issues,pull_requests",
    }
    assert captured["headers"]["X-MCP-Readonly"] == "true"


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


def _github_server():
    return McpRemoteServerConfig(
        name="github",
        transport="streamable-http",
        url="https://api.githubcopilot.com/mcp/",
        headers={
            "Authorization": "Bearer test-placeholder",
            "X-MCP-Toolsets": "repos,issues,pull_requests",
            "X-MCP-Readonly": "true",
        },
    )


def test_multipage_list_tools_discovery_still_works():
    pages = {
        None: SimpleNamespace(
            tools=[SimpleNamespace(name="list_issues", description="List issues", inputSchema={"type": "object", "properties": {}})],
            nextCursor="page-2",
        ),
        "page-2": SimpleNamespace(
            tools=[SimpleNamespace(name="get_issue", description="Get one issue", inputSchema={"type": "object", "properties": {}})],
            nextCursor=None,
        ),
    }

    class PagedSession:
        async def list_tools(self, cursor=None):
            return pages[cursor]

    adapter = MCPClientAdapter(servers=[_github_server()], session_factory=lambda _: FakeSessionContext(PagedSession()))

    names = [schema["function"]["name"] for schema in adapter.get_tools_schema()]
    assert names == ["mcp_github_list_issues", "mcp_github_get_issue"]


def test_github_schema_description_marks_mcp_source():
    adapter = MCPClientAdapter(servers=[_github_server()], session_factory=lambda _: FakeSessionContext(FakeSession()))

    schema = adapter.get_tools_schema()[0]
    assert schema["function"]["name"] == "mcp_github_echo"
    assert schema["function"]["description"].startswith("[github MCP]")


def test_write_tools_are_filtered_locally_during_discovery():
    remote_tools = [
        ("list_issues", "List issues"),
        ("get_issue", "Get a single issue"),
        ("create_issue", "Create a new issue"),
        ("update_issue", "Update an issue"),
        ("merge_pull_request", "Merge a pull request"),
        ("push_files", "Push files to a branch"),
        ("add_issue_comment", "Add a comment to an issue"),
    ]

    class GithubToolsSession:
        async def list_tools(self, cursor=None):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name=name, description=description, inputSchema={"type": "object", "properties": {}})
                    for name, description in remote_tools
                ],
                nextCursor=None,
            )

    adapter = MCPClientAdapter(servers=[_github_server()], session_factory=lambda _: FakeSessionContext(GithubToolsSession()))

    names = {schema["function"]["name"] for schema in adapter.get_tools_schema()}
    assert names == {"mcp_github_list_issues", "mcp_github_get_issue"}
    assert adapter.blocked_tools["github"] == [
        "create_issue",
        "update_issue",
        "merge_pull_request",
        "push_files",
        "add_issue_comment",
    ]


def test_discovery_failure_keeps_local_tools_running():
    def session_factory(_):
        raise RuntimeError("connection refused")

    adapter = MCPClientAdapter(servers=[_github_server()], session_factory=session_factory)
    registry = ToolRegistry(mcp_client_adapter=adapter)

    names = {schema["function"]["name"] for schema in registry.get_tools_schema()}
    assert "search_learning_notes" in names
    assert "web_search" in names
    assert adapter.get_tools_schema() == []
    assert adapter.discovery_errors["github"] == "connection refused"


def test_call_tool_arguments_reach_remote_tool():
    class RecordingSession(FakeSession):
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return SimpleNamespace(isError=False, structuredContent={"ok": True}, content=[])

    session = RecordingSession()
    server = McpRemoteServerConfig(name="demo", transport="stdio", command="demo")
    adapter = MCPClientAdapter(servers=[server], session_factory=lambda _: FakeSessionContext(session))
    adapter.get_tools_schema()

    result = adapter.execute("mcp_demo_echo", {"text": "hello", "count": 3})
    assert result["ok"] is True
    assert session.calls == [("echo", {"text": "hello", "count": 3})]


def test_remote_is_error_returns_mcp_remote_error():
    class ErrorSession(FakeSession):
        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                isError=True,
                structuredContent=None,
                content=[SimpleNamespace(type="text", text="boom")],
            )

    server = McpRemoteServerConfig(name="demo", transport="stdio", command="demo")
    adapter = MCPClientAdapter(servers=[server], session_factory=lambda _: FakeSessionContext(ErrorSession()))
    adapter.get_tools_schema()

    result = adapter.execute("mcp_demo_echo", {"text": "hello"})
    assert result["ok"] is False
    assert result["error"] == "mcp_remote_error"
    assert result["message"] == "boom"


def test_connect_failure_returns_sanitized_mcp_tool_failed():
    class SensitiveErrorSession(FakeSession):
        async def call_tool(self, name, arguments):
            raise RuntimeError(
                "connect failed: headers=[('authorization', 'Bearer ghp_fake_secret_123'), "
                "('password', 'hunter2')]"
            )

    server = McpRemoteServerConfig(name="demo", transport="stdio", command="demo")
    adapter = MCPClientAdapter(servers=[server], session_factory=lambda _: FakeSessionContext(SensitiveErrorSession()))
    adapter.get_tools_schema()

    result = adapter.execute("mcp_demo_echo", {"text": "hello"})
    assert result["ok"] is False
    assert result["error"] == "mcp_tool_failed"
    assert "ghp_fake_secret_123" not in result["message"]
    assert "hunter2" not in result["message"]
    assert "authorization" not in result["message"].lower()


def test_discovery_errors_are_sanitized():
    def session_factory(_):
        raise RuntimeError("401 Unauthorized: Authorization: Bearer ghp_fake_secret_456")

    adapter = MCPClientAdapter(servers=[_github_server()], session_factory=session_factory)

    assert adapter.get_tools_schema() == []
    message = adapter.discovery_errors["github"]
    assert "ghp_fake_secret_456" not in message
    assert "authorization" not in message.lower()


def test_write_guard_blocks_write_verbs():
    for name in [
        "create_issue",
        "updateIssue",
        "merge-pull-request",
        "push_files",
        "delete_issue",
        "add_issue_comment",
        "close_pull_request",
        "edit_file",
    ]:
        assert is_write_tool(name) is True, name


def test_write_guard_allows_read_tools():
    for name in [
        "list_issues",
        "get_issue",
        "search_repositories",
        "get_pull_request_diff",
        "list_releases",
        "list_stargazers",
        "list_commits",
    ]:
        assert is_write_tool(name) is False, name


def test_write_guard_checks_description_for_high_risk_verbs():
    assert is_write_tool("get_thing", "Create a new issue") is True
    assert is_write_tool("get_thing", "Delete a comment") is True
    assert is_write_tool("get_thing", "Get a single issue") is False
    assert is_write_tool("list_thing", "List issues for a repository") is False
