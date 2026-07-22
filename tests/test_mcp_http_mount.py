"""Tests for mounting the MCP HTTP app behind feature flags."""
from __future__ import annotations
import importlib
import sys


def test_mcp_http_mount_is_enabled_when_feature_flags_are_on(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    monkeypatch.setenv("MCP_HTTP_ENABLED", "true")
    monkeypatch.setenv("MCP_HTTP_PATH", "/mcp")
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    paths = [getattr(route, "path", None) for route in module.app.routes]
    assert "/mcp" in paths
