"""Manual safety check for the MCP client (read-only GitHub MVP).

Prints discovered public tool names, locally blocked write tools, and a safe
summary of discovery errors. Never prints headers, tokens, PATs, or the full
server configuration. Requires no network access when the MCP client is off.

Usage:
    python scripts/check_mcp_client.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mcp.client import MCPClientAdapter
from app.mcp.settings import is_mcp_client_enabled, load_mcp_client_servers


def main() -> int:
    if not is_mcp_client_enabled():
        print("MCP_CLIENT_ENABLED is not 'true'; the MCP client is off.")
        print("Local Agent tools are unaffected.")
        return 0

    try:
        servers = load_mcp_client_servers()
    except RuntimeError as exc:
        # Settings errors name variables/fields but never echo their values.
        print(f"MCP client configuration error: {exc}")
        return 1

    if not servers:
        print("MCP_CLIENT_ENABLED=true but MCP_CLIENT_SERVERS is empty.")
        return 1

    print(f"Configured servers: {', '.join(sorted({s.name for s in servers}))}")
    adapter = MCPClientAdapter(servers=servers)
    schemas = adapter.refresh()

    if not schemas:
        print("No tools discovered.")
    else:
        print(f"Discovered tools ({len(schemas)}):")
        for schema in schemas:
            print(f"- {schema['function']['name']}")

    for server_name, blocked in adapter.blocked_tools.items():
        print(f"Locally blocked tools from {server_name}:")
        for entry in blocked or []:
            # Entries are {"name": ..., "reason": ...} dicts. Defensive
            # handling keeps the check script alive even if the structure
            # ever changes; never prints arguments, headers, or tokens.
            if isinstance(entry, dict):
                tool_name = str(entry.get("name") or "unknown")
                reason = str(entry.get("reason") or "unknown")
            elif isinstance(entry, str):
                tool_name, reason = entry, "unknown"
            else:
                tool_name, reason = repr(entry), "unknown"
            print(f"- {tool_name}: {reason}")

    if adapter.discovery_errors:
        print("Discovery errors (safe summary):")
        for server_name, message in adapter.discovery_errors.items():
            print(f"- {server_name}: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
