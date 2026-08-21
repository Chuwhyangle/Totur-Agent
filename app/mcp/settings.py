"""Feature flags and runtime settings for MCP server and client."""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

from app.mcp.github_policy import (
    GITHUB_FORBIDDEN_HEADERS,
    GITHUB_READ_ONLY_ALLOWED_TOOLS,
    GITHUB_REQUIRED_TOOLSETS,
    is_github_server,
    validate_github_hosted_mcp_endpoint,
)

# Re-exported for backward compatibility with earlier imports.
GITHUB_MCP_HOST = "api.githubcopilot.com"
ALLOWED_GITHUB_TOOLSETS = frozenset(GITHUB_REQUIRED_TOOLSETS)

_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
# CR, LF, NUL and any other C0/C1 control characters are never valid in
# header names or values and are rejected before reaching an HTTP client.
_HEADER_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def expand_env_refs(raw: str) -> str:
    """Expand ${NAME} references against the process environment, fail-closed.

    python-dotenv only interpolates values it parses from a .env file; values
    provided by the real process environment keep their literal ${NAME}
    references. This small resolver covers both cases deterministically:
    an undefined reference raises RuntimeError naming the variable only, and
    never embeds the variable's value in the message. Use $$ to emit a
    literal $.
    """
    escaped = raw.replace("$$", "\x00")

    def _resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS references undefined environment variable: {name}"
            )
        return value

    expanded = _ENV_REF_PATTERN.sub(_resolve, escaped)
    return expanded.replace("\x00", "$")

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def is_mcp_server_enabled() -> bool:
    load_dotenv()
    return _env_bool("MCP_SERVER_ENABLED")

def is_mcp_http_enabled() -> bool:
    load_dotenv()
    return is_mcp_server_enabled() and _env_bool("MCP_HTTP_ENABLED")

def is_mcp_client_enabled() -> bool:
    load_dotenv()
    return _env_bool("MCP_CLIENT_ENABLED")

def get_mcp_auth_token() -> str | None:
    load_dotenv()
    return os.getenv("MCP_AUTH_TOKEN", "").strip() or None

def get_mcp_http_path() -> str:
    load_dotenv()
    path = os.getenv("MCP_HTTP_PATH", "/mcp").strip() or "/mcp"
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/mcp"

def get_mcp_client_timeout_seconds() -> float:
    load_dotenv()
    try:
        timeout = float(os.getenv("MCP_CLIENT_TIMEOUT_SECONDS", "10").strip())
    except ValueError:
        return 10.0
    return min(max(timeout, 1.0), 60.0)

def get_mcp_client_retry_seconds() -> float:
    load_dotenv()
    try:
        retry_seconds = float(os.getenv("MCP_CLIENT_RETRY_SECONDS", "30").strip())
    except ValueError:
        return 30.0
    return min(max(retry_seconds, 0.0), 3600.0)

def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class McpRemoteServerConfig:
    name: str
    transport: str
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    env: dict[str, str] | None = None
    # Server-level tool policy: when non-empty, only these remote tool names
    # may be discovered or executed. GitHub hosted MCP configs are required
    # to set a non-empty allowlist (a subset of the code-level read-only
    # allowlist); other servers may omit it to keep legacy behavior.
    allowed_tools: tuple[str, ...] = ()

    def __repr__(self) -> str:
        # Header/env values can hold the PAT; never embed them in a repr so
        # an accidentally logged config cannot leak secrets.
        headers = {key: "<redacted>" for key in (self.headers or {})}
        env = {key: "<redacted>" for key in (self.env or {})}
        return (
            f"McpRemoteServerConfig(name={self.name!r}, transport={self.transport!r}, "
            f"command={self.command!r}, args={self.args!r}, cwd={self.cwd!r}, "
            f"url={self.url!r}, headers={headers!r}, env={env!r}, "
            f"allowed_tools={self.allowed_tools!r})"
        )


def _parse_headers(index: int, raw_headers: object) -> dict[str, str]:
    """Normalize a headers mapping into a case-folded, safe dict.

    Header names are compared case-insensitively per HTTP semantics, so the
    result is keyed by the lower-case name. Rejects empty names, control
    characters (CR/LF/NUL, ...) in names or values, and duplicate headers
    that differ only in case. Never echoes header values in errors.
    """
    if not isinstance(raw_headers, dict):
        raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].headers must be an object")
    parsed: dict[str, str] = {}
    for raw_key, raw_value in raw_headers.items():
        key = str(raw_key).strip()
        if not key:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].headers contains an empty header name"
            )
        if _HEADER_CONTROL_CHARS.search(key):
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].headers contains an invalid header name"
            )
        value = str(raw_value).strip()
        if _HEADER_CONTROL_CHARS.search(value):
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].headers contains an invalid header value"
            )
        folded = key.lower()
        if folded in parsed:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].headers contains a duplicate header: {folded}"
            )
        parsed[folded] = value
    return parsed


def _validate_bearer_token_not_empty(index: int, parsed: dict[str, str]) -> None:
    """Shared check for any server: a Bearer Authorization may never be empty."""
    authorization = parsed.get("authorization")
    if authorization is None:
        return
    scheme, _, token = authorization.partition(" ")
    if scheme.strip().lower() == "bearer" and not token.strip():
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers.Authorization has an empty "
            "Bearer token; set the referenced environment variable "
            "(e.g. GITHUB_MCP_PAT) to a non-empty value before enabling "
            "the MCP client. When both live in .env, define the token "
            "variable above MCP_CLIENT_SERVERS."
        )


def _validate_github_headers(
    index: int,
    parsed: dict[str, str],
) -> dict[str, str]:
    """Enforce GitHub hosted MCP headers and return the canonical dict.

    Fail-closed: Authorization, X-MCP-Readonly and X-MCP-Toolsets are all
    mandatory with exact semantics; headers that would widen the tool
    surface are rejected. The returned dict is the stable, canonical format
    handed to the HTTP client (only the three safe headers survive).
    Errors name the offending header but never include its value.
    """
    for forbidden in sorted(GITHUB_FORBIDDEN_HEADERS & parsed.keys()):
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers must not set {forbidden} "
            "for the GitHub hosted MCP server"
        )

    authorization = parsed.get("authorization")
    if authorization is None:
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers is missing Authorization "
            "for the GitHub hosted MCP server"
        )
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.strip().lower() != "bearer":
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers.Authorization must use "
            "the Bearer scheme for the GitHub hosted MCP server"
        )
    token = token.strip()
    if not token:
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers.Authorization has an empty "
            "Bearer token; set the referenced environment variable "
            "(e.g. GITHUB_MCP_PAT) to a non-empty value before enabling "
            "the MCP client. When both live in .env, define the token "
            "variable above MCP_CLIENT_SERVERS."
        )
    if any(char.isspace() for char in token) or _HEADER_CONTROL_CHARS.search(token):
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers.Authorization contains an "
            "invalid Bearer token"
        )

    readonly = parsed.get("x-mcp-readonly")
    if readonly is None or readonly.strip().lower() != "true":
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}] targets the GitHub hosted MCP server; "
            'headers must include X-MCP-Readonly: "true"'
        )

    toolsets_raw = parsed.get("x-mcp-toolsets")
    if toolsets_raw is None or not toolsets_raw.strip():
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}] targets the GitHub hosted MCP server; "
            "headers must include X-MCP-Toolsets"
        )
    requested = {
        part.strip().lower() for part in toolsets_raw.split(",") if part.strip()
    }
    if requested != GITHUB_REQUIRED_TOOLSETS:
        missing = sorted(GITHUB_REQUIRED_TOOLSETS - requested)
        extra = sorted(requested - GITHUB_REQUIRED_TOOLSETS)
        detail_parts: list[str] = []
        if missing:
            detail_parts.append(f"missing {', '.join(missing)}")
        if extra:
            detail_parts.append(f"unsupported {', '.join(extra)}")
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].headers.X-MCP-Toolsets must be exactly "
            f"repos,issues,pull_requests ({'; '.join(detail_parts)})"
        )

    # Canonical, stable format for the HTTP client. Only these three headers
    # survive; anything else on a GitHub config is dropped by design.
    return {
        "Authorization": f"Bearer {token}",
        "X-MCP-Readonly": "true",
        "X-MCP-Toolsets": "repos,issues,pull_requests",
    }


def _parse_allowed_tools(
    index: int,
    raw_allowed_tools: object,
    is_github: bool,
) -> tuple[str, ...]:
    """Parse and validate the server-level allowed_tools list.

    Must be a non-empty array of unique, non-empty strings. For GitHub it is
    mandatory and must be a subset of the code-level read-only allowlist.
    Errors name the field only; tool names are not secrets but values are
    still not echoed wholesale.
    """
    if raw_allowed_tools is None:
        if is_github:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].allowed_tools is required for "
                "the GitHub hosted MCP server"
            )
        return ()
    if not isinstance(raw_allowed_tools, list):
        raise RuntimeError(
            f"MCP_CLIENT_SERVERS[{index}].allowed_tools must be an array of tool names"
        )
    if not raw_allowed_tools:
        raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].allowed_tools must not be empty")
    tools: list[str] = []
    seen: set[str] = set()
    for raw_tool in raw_allowed_tools:
        if not isinstance(raw_tool, str):
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].allowed_tools must contain only strings"
            )
        tool = raw_tool.strip()
        if not tool:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].allowed_tools must not contain empty strings"
            )
        if tool in seen:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].allowed_tools must not contain duplicates"
            )
        seen.add(tool)
        tools.append(tool)
    if is_github:
        outside = sorted(set(tools) - GITHUB_READ_ONLY_ALLOWED_TOOLS)
        if outside:
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}].allowed_tools contains tools outside "
                f"the GitHub read-only allowlist: {', '.join(outside)}"
            )
    return tuple(tools)


def load_mcp_client_servers() -> list[McpRemoteServerConfig]:
    load_dotenv()
    if not is_mcp_client_enabled():
        return []
    raw = os.getenv("MCP_CLIENT_SERVERS", "").strip()
    if not raw:
        return []
    raw = expand_env_refs(raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("MCP_CLIENT_SERVERS must be valid JSON") from exc
    if not isinstance(payload, list):
        raise RuntimeError("MCP_CLIENT_SERVERS must be a JSON array")
    servers: list[McpRemoteServerConfig] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}] must be an object")
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "stdio").strip().lower()
        if transport == "http":
            transport = "streamable-http"
        if not name:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].name is required")
        if transport not in {"stdio", "streamable-http"}:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].transport must be stdio or streamable-http")
        args = item.get("args") or []
        env = item.get("env") or {}
        if not isinstance(args, list):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].args must be an array")
        if not isinstance(env, dict):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].env must be an object")
        command = str(item.get("command") or "").strip() or None
        url = str(item.get("url") or "").strip() or None
        if transport == "stdio" and not command:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].command is required")
        if transport == "streamable-http" and not url:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].url is required")

        # GitHub policy applies when the name or the URL host matches GitHub.
        is_github = is_github_server(name, url)

        # P0-1: GitHub endpoint validation runs here, before any network
        # connection can be established. The URL is replaced by the
        # canonical endpoint on success.
        if is_github:
            if transport != "streamable-http":
                raise RuntimeError(
                    f"MCP_CLIENT_SERVERS[{index}] uses the GitHub name/host and "
                    "must use transport streamable-http"
                )
            try:
                url = validate_github_hosted_mcp_endpoint(url)
            except ValueError as exc:
                raise RuntimeError(
                    f"MCP_CLIENT_SERVERS[{index}].url is not a valid official "
                    f"GitHub hosted MCP endpoint: {exc}"
                ) from None

        parsed_headers = _parse_headers(index, item.get("headers") or {})
        _validate_bearer_token_not_empty(index, parsed_headers)
        if is_github:
            headers = _validate_github_headers(index, parsed_headers)
        else:
            headers = parsed_headers or None

        allowed_tools = _parse_allowed_tools(
            index, item.get("allowed_tools"), is_github
        )

        servers.append(McpRemoteServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=tuple(str(arg) for arg in args),
            cwd=str(item["cwd"]) if item.get("cwd") else None,
            url=url,
            headers=headers,
            env={str(key): str(value) for key, value in env.items()} or None,
            allowed_tools=allowed_tools,
        ))
    return servers
