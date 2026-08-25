"""Tests for the credential-free GitHub MCP status endpoint."""

from __future__ import annotations

from app.api.routes import mcp as mcp_route


def test_github_mcp_status_is_safe_when_disabled(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "false")
    monkeypatch.setenv("GITHUB_MCP_PROJECTS", "Chuwhyangle/Totur-Agent,example/other")

    payload = mcp_route.github_mcp_status()

    assert payload["status"] == "disabled"
    assert payload["enabled"] is False
    assert payload["readonly"] is True
    assert [item["full_name"] for item in payload["projects"]] == [
        "Chuwhyangle/Totur-Agent",
        "example/other",
    ]
    assert "headers" not in payload
    assert "token" not in str(payload).lower()


def test_github_mcp_status_reports_tools_without_credentials(monkeypatch):
    class FakeServer:
        name = "github"
        transport = "streamable-http"
        url = "https://api.githubcopilot.com/mcp/"

    class FakeAdapter:
        blocked_tools = {"github": ["push_files"]}
        discovery_errors = {}

        def __init__(self, servers):
            assert servers == [server]

        def refresh(self):
            return [
                {"function": {"name": "mcp_github_search_code"}},
                {"function": {"name": "mcp_github_get_file_contents"}},
            ]

    server = FakeServer()
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setattr(mcp_route, "load_mcp_client_servers", lambda: [server])
    monkeypatch.setattr(mcp_route, "MCPClientAdapter", FakeAdapter)

    payload = mcp_route.github_mcp_status()

    assert payload["status"] == "connected"
    assert payload["enabled"] is True
    assert payload["server_name"] == "github"
    assert payload["tool_count"] == 2
    assert payload["blocked_write_tool_count"] == 1
    assert payload["tools"] == [
        "mcp_github_search_code",
        "mcp_github_get_file_contents",
    ]


def test_github_mcp_status_does_not_fail_when_config_is_invalid(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setattr(
        mcp_route,
        "load_mcp_client_servers",
        lambda: (_ for _ in ()).throw(RuntimeError("MCP configuration error")),
    )

    payload = mcp_route.github_mcp_status()

    assert payload["status"] == "configuration_error"
    assert payload["enabled"] is True
    assert payload["tool_count"] == 0
