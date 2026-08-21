"""Local defense-in-depth: keep write-capable remote MCP tools out of the Agent.

IMPORTANT: this module is only the SECOND layer of defense, not the primary
security boundary. The primary boundary is the per-server ``allowed_tools``
allowlist enforced in ``app/mcp/client.py`` (policy constants live in
``app/mcp/github_policy.py``); GitHub hosted MCP configs must pass a
code-level read-only allowlist, so unknown tools are blocked by default.

write_guard remains as an independent name/description filter applied to
every discovered remote tool, so obvious write operations
(create/update/delete/merge/push, ...) never reach the ReAct loop even for
servers without an explicit allowlist.

Rules are deliberately conservative and name-based: remote MCP tools follow
a verb_noun naming convention, so verb tokens are a reliable signal. A small
set of high-risk verbs is additionally checked in the description as defense
in depth. Keep this module self-contained so the policy is reviewable and
testable in one place.
"""
from __future__ import annotations

import re

# Name tokens that mark a tool as a write operation. Nouns like "release" or
# "archive" are intentionally absent so read tools (list_releases, ...) pass.
BLOCKED_VERB_TOKENS = frozenset({
    "add",
    "approve",
    "assign",
    "close",
    "create",
    "delete",
    "dismiss",
    "edit",
    "fork",
    "lock",
    "merge",
    "push",
    "remove",
    "rename",
    "reopen",
    "restore",
    "revert",
    "star",
    "subscribe",
    "transfer",
    "unassign",
    "unlock",
    "unstar",
    "unsubscribe",
    "update",
})

# High-risk verbs also rejected when they appear in the tool description.
DESCRIPTION_BLOCKED_VERBS = frozenset({"create", "delete", "merge", "push"})

_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(text: str) -> set[str]:
    normalized = _CAMEL_SPLIT.sub(" ", text or "")
    return {part.lower() for part in re.split(r"[^A-Za-z0-9]+", normalized) if part}


def is_write_tool(name: str, description: str = "") -> bool:
    """True when a remote tool is an obvious write operation and must be blocked."""
    if _tokens(name) & BLOCKED_VERB_TOKENS:
        return True
    return bool(_tokens(description) & DESCRIPTION_BLOCKED_VERBS)
