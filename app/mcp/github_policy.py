"""GitHub hosted MCP security policy, centralized in one module.

Everything specific to the GitHub hosted MCP server lives here: the official
endpoint rules, the mandatory read-only headers, the code-level tool
allowlist, and the block reason identifiers.

Two layers consume this policy:

- ``app/mcp/settings.py`` enforces it at configuration load time, before any
  network connection can be established (fail-closed: invalid configs raise).
- ``app/mcp/client.py`` enforces the allowlist during tool discovery and
  again right before ``execute()`` sends a remote request.

Keep this module self-contained: no imports from the rest of ``app.mcp`` so
the policy stays reviewable in one place.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Official GitHub hosted MCP endpoint. A GitHub PAT may only ever be sent to
# this host over HTTPS; everything else is rejected at config load.
GITHUB_MCP_HOST = "api.githubcopilot.com"
GITHUB_CANONICAL_ENDPOINT = "https://api.githubcopilot.com/mcp/"

# The only path shapes accepted for the canonical endpoint in this phase.
GITHUB_ALLOWED_PATHS = frozenset({"/mcp", "/mcp/"})

# GitHub toolset scope. The requested set must be exactly equal to this one:
# no missing toolset, no extra toolset.
GITHUB_REQUIRED_TOOLSETS = frozenset({"repos", "issues", "pull_requests"})

# Server-level tool allowlist for the GitHub hosted MCP server. These are
# read-only tool names only; anything else (including unknown tools added by
# GitHub later) is blocked by default. Do not widen this list just to expose
# more tools: every entry must be certain it cannot mutate remote state.
GITHUB_READ_ONLY_ALLOWED_TOOLS = frozenset({
    "get_file_contents",
    "search_code",
    "search_repositories",
    "issue_read",
    "list_issues",
    "pull_request_read",
    "search_pull_requests",
})

# Headers that would widen the GitHub tool surface. Rejected outright for
# GitHub hosted MCP configs (header names compared case-insensitively).
GITHUB_FORBIDDEN_HEADERS = frozenset({
    "x-mcp-tools",
    "x-mcp-exclude-tools",
    "x-mcp-insiders",
})

# Block reason identifiers recorded in MCPClientAdapter.blocked_tools.
BLOCK_REASON_NOT_IN_ALLOWLIST = "not_in_allowlist"
BLOCK_REASON_WRITE_GUARD = "write_guard"


def is_github_server_name(name: str) -> bool:
    """True when the server name is ``github``, case-insensitive."""
    return (name or "").strip().lower() == "github"


def url_uses_github_host(url: str | None) -> bool:
    """True when the URL hostname is exactly the GitHub hosted MCP host."""
    if not url:
        return False
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return hostname == GITHUB_MCP_HOST


def is_github_server(name: str, url: str | None) -> bool:
    """True when the GitHub security policy applies to a server config.

    Either condition triggers the full policy: the server is named
    ``github`` (case-insensitive), or its URL points at the GitHub hosted
    MCP host. This prevents a rename from bypassing the policy.
    """
    return is_github_server_name(name) or url_uses_github_host(url)


def validate_github_hosted_mcp_endpoint(url: str | None) -> str:
    """Validate a GitHub hosted MCP URL and return the canonical endpoint.

    Fail-closed: any deviation raises ``ValueError``. Error messages name
    the offending field and the expected value only; they never include the
    URL, Authorization header, PAT, or the full configuration.
    """
    if not url or not url.strip():
        raise ValueError("url is required")
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        raise ValueError("url is not a valid endpoint") from None
    if parsed.scheme.lower() != "https":
        raise ValueError("scheme must be https")
    if (parsed.hostname or "").lower() != GITHUB_MCP_HOST:
        raise ValueError(f"hostname must be exactly {GITHUB_MCP_HOST}")
    if parsed.port not in (None, 443):
        raise ValueError("port must be empty or 443")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("userinfo must be empty")
    if parsed.query or parsed.fragment:
        raise ValueError("query and fragment must be empty")
    if parsed.path not in GITHUB_ALLOWED_PATHS:
        raise ValueError("path must be /mcp or /mcp/")
    return GITHUB_CANONICAL_ENDPOINT
