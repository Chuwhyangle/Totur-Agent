"""Feature flags and runtime settings for MCP server and client."""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Hosted GitHub MCP guardrails. The remote is asked for read-only tooling via
# headers, and the local settings validate that configuration explicitly.
GITHUB_MCP_HOST = "api.githubcopilot.com"
ALLOWED_GITHUB_TOOLSETS = frozenset({"repos", "issues", "pull_requests"})

_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


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

def _validate_remote_headers(
    index: int,
    name: str,
    transport: str,
    url: str,
    headers: dict[str, str],
) -> None:
    """Reject unsafe remote MCP header configuration without echoing values."""
    for key, value in headers.items():
        if key.lower() == "authorization":
            scheme, _, token = value.partition(" ")
            if scheme.strip().lower() == "bearer" and not token.strip():
                raise RuntimeError(
                    f"MCP_CLIENT_SERVERS[{index}].headers.Authorization has an empty "
                    "Bearer token; set the referenced environment variable "
                    "(e.g. GITHUB_MCP_PAT) to a non-empty value before enabling "
                    "the MCP client. When both live in .env, define the token "
                    "variable above MCP_CLIENT_SERVERS."
                )
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        host = ""
    is_github = name.lower() == "github" or host == GITHUB_MCP_HOST
    if transport == "streamable-http" and is_github:
        if str(headers.get("X-MCP-Readonly", "")).strip().lower() != "true":
            raise RuntimeError(
                f"MCP_CLIENT_SERVERS[{index}] targets the GitHub hosted MCP server; "
                "headers must include X-MCP-Readonly: \"true\""
            )
        toolsets = str(headers.get("X-MCP-Toolsets", "")).strip()
        if toolsets:
            requested = {part.strip().lower() for part in toolsets.split(",") if part.strip()}
            invalid = sorted(requested - ALLOWED_GITHUB_TOOLSETS)
            if invalid:
                raise RuntimeError(
                    f"MCP_CLIENT_SERVERS[{index}] requests unsupported GitHub toolsets: "
                    f"{', '.join(invalid)}; only repos, issues, pull_requests "
                    "are allowed in this phase"
                )


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
        headers = item.get("headers") or {}
        env = item.get("env") or {}
        if not isinstance(args, list):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].args must be an array")
        if not isinstance(headers, dict):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].headers must be an object")
        if not isinstance(env, dict):
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].env must be an object")
        command = str(item.get("command") or "").strip() or None
        url = str(item.get("url") or "").strip() or None
        if transport == "stdio" and not command:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].command is required")
        if transport == "streamable-http" and not url:
            raise RuntimeError(f"MCP_CLIENT_SERVERS[{index}].url is required")
        parsed_headers = {str(key): str(value) for key, value in headers.items()}
        _validate_remote_headers(index, name, transport, url, parsed_headers)
        servers.append(McpRemoteServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=tuple(str(arg) for arg in args),
            cwd=str(item["cwd"]) if item.get("cwd") else None,
            url=url,
            headers=parsed_headers or None,
            env={str(key): str(value) for key, value in env.items()} or None,
        ))
    return servers
