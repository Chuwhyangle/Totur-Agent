"""Tests for MCP client settings: env expansion and GitHub read-only guardrails.

No test in this file performs network access, and no real PAT is used or
printed. Assertions only compare against placeholder token values.
"""
from __future__ import annotations

import json

import pytest

from app.mcp.settings import (
    McpRemoteServerConfig,
    expand_env_refs,
    load_mcp_client_servers,
)


FAKE_PAT = "test-pat-placeholder-not-a-real-token"

# Never exists in any developer .env; used to simulate a missing variable.
MISSING_VAR = "MCP_MISSING_PAT_7F3A9C"

# Code-level read-only allowlist from app/mcp/github_policy.py.
GITHUB_READ_TOOLS = [
    "get_file_contents",
    "search_code",
    "search_repositories",
    "issue_read",
    "list_issues",
    "pull_request_read",
    "search_pull_requests",
]


@pytest.fixture(autouse=True)
def mcp_env(monkeypatch):
    """Pin MCP env vars so a developer .env file cannot leak into tests."""
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "false")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", "[]")
    monkeypatch.setenv("GITHUB_MCP_PAT", FAKE_PAT)


def _servers_json(header_value: str, url: str = "https://api.githubcopilot.com/mcp/") -> str:
    return json.dumps([
        {
            "name": "github",
            "transport": "streamable-http",
            "url": url,
            "headers": {
                "Authorization": header_value,
                "X-MCP-Toolsets": "repos,issues,pull_requests",
                "X-MCP-Readonly": "true",
            },
            "allowed_tools": GITHUB_READ_TOOLS,
        }
    ])


def test_mcp_client_disabled_by_default(monkeypatch):
    """Unconfigured users (flag off) never parse MCP_CLIENT_SERVERS."""
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "false")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json(f"Bearer ${{{MISSING_VAR}}}"))

    assert load_mcp_client_servers() == []


def test_parse_github_streamable_http_with_env_expansion(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("GITHUB_MCP_PAT", FAKE_PAT)
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json("Bearer ${GITHUB_MCP_PAT}"))

    servers = load_mcp_client_servers()

    assert len(servers) == 1
    server = servers[0]
    assert isinstance(server, McpRemoteServerConfig)
    assert server.name == "github"
    assert server.transport == "streamable-http"
    assert server.url == "https://api.githubcopilot.com/mcp/"
    assert server.headers["Authorization"] == f"Bearer {FAKE_PAT}"
    assert server.headers["X-MCP-Readonly"] == "true"
    assert server.headers["X-MCP-Toolsets"] == "repos,issues,pull_requests"


def test_http_transport_is_normalized_to_streamable_http(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["transport"] = "http"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    servers = load_mcp_client_servers()

    assert servers[0].transport == "streamable-http"


def test_streamable_http_server_without_url_is_rejected(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_CLIENT_SERVERS",
        json.dumps([{"name": "github", "transport": "streamable-http", "headers": {}}]),
    )

    with pytest.raises(RuntimeError, match="url is required"):
        load_mcp_client_servers()


def test_missing_env_var_reference_is_rejected_without_value(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json(f"Bearer ${{{MISSING_VAR}}}"))

    with pytest.raises(RuntimeError) as exc_info:
        load_mcp_client_servers()

    message = str(exc_info.value)
    # Names the missing variable, never its (nonexistent) value.
    assert MISSING_VAR in message
    assert "Bearer" not in message


def test_empty_bearer_token_is_rejected(monkeypatch):
    """A literal 'Bearer ' header must never produce a live config."""
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json("Bearer "))

    with pytest.raises(RuntimeError, match="empty Bearer token"):
        load_mcp_client_servers()


def test_empty_env_value_expansion_does_not_create_empty_bearer(monkeypatch):
    """Even when the referenced variable exists but is empty, fail closed."""
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("GITHUB_MCP_PAT", "")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json("Bearer ${GITHUB_MCP_PAT}"))

    with pytest.raises(RuntimeError, match="empty Bearer token"):
        load_mcp_client_servers()


def test_config_errors_never_expose_token_value(monkeypatch):
    """A failing config must not leak the (placeholder) token in errors."""
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("GITHUB_MCP_PAT", FAKE_PAT)
    # Missing URL forces an error while the token itself is valid.
    monkeypatch.setenv(
        "MCP_CLIENT_SERVERS",
        json.dumps([
            {
                "name": "github",
                "transport": "streamable-http",
                "headers": {
                    "Authorization": f"Bearer ${{GITHUB_MCP_PAT}}",
                    "X-MCP-Toolsets": "repos,issues,pull_requests",
                    "X-MCP-Readonly": "true",
                },
            }
        ]),
    )

    with pytest.raises(RuntimeError) as exc_info:
        load_mcp_client_servers()

    assert FAKE_PAT not in str(exc_info.value)


def test_github_server_requires_readonly_header(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_CLIENT_SERVERS",
        json.dumps([
            {
                "name": "github",
                "transport": "streamable-http",
                "url": "https://api.githubcopilot.com/mcp/",
                "headers": {
                    "Authorization": f"Bearer ${{GITHUB_MCP_PAT}}",
                    "X-MCP-Toolsets": "repos,issues,pull_requests",
                },
            }
        ]),
    )

    with pytest.raises(RuntimeError, match="X-MCP-Readonly"):
        load_mcp_client_servers()


def test_github_server_rejects_readonly_false(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"]["X-MCP-Readonly"] = "false"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="X-MCP-Readonly"):
        load_mcp_client_servers()


def test_github_toolsets_restricted_to_readonly_scope(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"]["X-MCP-Toolsets"] = "repos,issues,codespaces"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="codespaces"):
        load_mcp_client_servers()


def test_allowed_github_toolsets_are_accepted(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json("Bearer ${GITHUB_MCP_PAT}"))

    servers = load_mcp_client_servers()

    assert servers[0].headers["X-MCP-Toolsets"] == "repos,issues,pull_requests"


def test_expand_env_refs_resolves_existing_variable(monkeypatch):
    monkeypatch.setenv("MCP_REF_TEST_VAR", "ref-value")

    assert expand_env_refs("a=${MCP_REF_TEST_VAR}") == "a=ref-value"


def test_expand_env_refs_raises_on_undefined_variable(monkeypatch):
    monkeypatch.delenv("MCP_REF_TEST_MISSING", raising=False)

    with pytest.raises(RuntimeError, match="MCP_REF_TEST_MISSING"):
        expand_env_refs("a=${MCP_REF_TEST_MISSING}")


def test_expand_env_refs_double_dollar_escapes(monkeypatch):
    assert expand_env_refs("a=$${NOT_A_REF}") == "a=${NOT_A_REF}"


def test_expand_env_refs_ignores_plain_dollar(monkeypatch):
    assert expand_env_refs("a=$5") == "a=$5"


# --- Endpoint guardrails (P0-1) ---


def test_github_name_with_non_github_url_is_rejected(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_CLIENT_SERVERS",
        _servers_json("Bearer ${GITHUB_MCP_PAT}", url="https://evil.example.com/mcp/"),
    )

    with pytest.raises(RuntimeError, match="official"):
        load_mcp_client_servers()


def test_github_http_url_is_rejected(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv(
        "MCP_CLIENT_SERVERS",
        _servers_json("Bearer ${GITHUB_MCP_PAT}", url="http://api.githubcopilot.com/mcp/"),
    )

    with pytest.raises(RuntimeError, match="https"):
        load_mcp_client_servers()


def test_official_https_github_url_is_accepted(monkeypatch):
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", _servers_json("Bearer ${GITHUB_MCP_PAT}"))

    servers = load_mcp_client_servers()

    assert servers[0].url == "https://api.githubcopilot.com/mcp/"


# --- Mandatory headers (P0-2) ---


def test_github_server_requires_authorization(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    del payload[0]["headers"]["Authorization"]
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="Authorization"):
        load_mcp_client_servers()


def test_github_server_rejects_basic_authorization(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"]["Authorization"] = "Basic abc"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="Bearer scheme"):
        load_mcp_client_servers()


def test_github_server_requires_toolsets(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    del payload[0]["headers"]["X-MCP-Toolsets"]
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="X-MCP-Toolsets"):
        load_mcp_client_servers()


def test_github_toolsets_missing_one_is_rejected(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"]["X-MCP-Toolsets"] = "repos,issues"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="pull_requests"):
        load_mcp_client_servers()


def test_github_header_names_are_case_insensitive(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"] = {
        "authorization": "Bearer ${GITHUB_MCP_PAT}",
        "x-mcp-toolsets": "repos,issues,pull_requests",
        "x-mcp-readonly": "true",
    }
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    servers = load_mcp_client_servers()

    assert servers[0].headers == {
        "Authorization": f"Bearer {FAKE_PAT}",
        "X-MCP-Readonly": "true",
        "X-MCP-Toolsets": "repos,issues,pull_requests",
    }


def test_github_duplicate_header_case_variants_are_rejected(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["headers"]["x-mcp-readonly"] = "true"
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="duplicate"):
        load_mcp_client_servers()


# --- allowed_tools allowlist (P0-3) ---


def test_github_server_requires_allowed_tools(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    del payload[0]["allowed_tools"]
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="allowed_tools"):
        load_mcp_client_servers()


def test_github_server_rejects_empty_allowed_tools(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["allowed_tools"] = []
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="not be empty"):
        load_mcp_client_servers()


def test_github_allowlist_rejects_non_allowlist_tool(monkeypatch):
    payload = json.loads(_servers_json("Bearer ${GITHUB_MCP_PAT}"))
    payload[0]["allowed_tools"] = ["create_issue"]
    monkeypatch.setenv("MCP_CLIENT_ENABLED", "true")
    monkeypatch.setenv("MCP_CLIENT_SERVERS", json.dumps(payload))

    with pytest.raises(RuntimeError, match="outside"):
        load_mcp_client_servers()
