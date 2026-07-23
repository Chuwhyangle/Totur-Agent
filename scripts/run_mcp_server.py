"""Run Tutor Agent MCP server over stdio."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mcp.server import run_stdio


if __name__ == "__main__":
    run_stdio()
