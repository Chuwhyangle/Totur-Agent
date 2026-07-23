"""Tests for mounting the MCP HTTP app behind feature flags."""
from __future__ import annotations
import importlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.mcp.server import MCPMountPathMiddleware


def test_mcp_http_mount_is_enabled_when_feature_flags_are_on(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    monkeypatch.setenv("MCP_HTTP_ENABLED", "true")
    monkeypatch.setenv("MCP_HTTP_PATH", "/mcp")
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    paths = [getattr(route, "path", None) for route in module.app.routes]
    assert "/mcp" in paths
    assert any(middleware.cls is MCPMountPathMiddleware for middleware in module.app.user_middleware)


def test_exact_mcp_mount_path_is_served_without_redirect():
    async def endpoint(request):
        return PlainTextResponse("ok")

    mounted_app = Starlette(routes=[Route("/", endpoint)])
    app = FastAPI()
    app.add_middleware(MCPMountPathMiddleware, mount_path="/mcp")
    app.mount("/mcp", mounted_app)

    with TestClient(app) as client:
        response = client.get("/mcp", follow_redirects=False)

    assert response.status_code == 200
    assert response.text == "ok"
    assert response.history == []
