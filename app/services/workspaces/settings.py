"""Workspace feature flags and domain limits."""

import os

from dotenv import load_dotenv


WORKSPACE_USER_ID_MAX_LENGTH = 64
WORKSPACE_AGENT_INSTRUCTIONS_MAX_LENGTH = 8000
WORKSPACE_NAME_MAX_LENGTH = 120
WORKSPACE_DESCRIPTION_MAX_LENGTH = 4000


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_workspaces_enabled() -> bool:
    """Return whether the Workspace API is enabled."""

    load_dotenv()
    return _env_bool("ENABLE_WORKSPACES", False)
