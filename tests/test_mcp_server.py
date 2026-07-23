"""Tests for Tutor Agent MCP server primitives."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import time

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

from app.mcp import tools as mcp_tools
from app.mcp.server import mcp


def test_mcp_server_lists_business_tools_resources_and_prompts():
    async def exercise() -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert {"search_learning_notes", "interview_jd_search", "score_jd_skill_fit", "generate_quiz"} <= tool_names

            resources = await session.list_resources()
            resource_uris = {str(resource.uri) for resource in resources.resources}
            assert {"manifest://index", "docs://catalog", "reports://catalog", "metrics://tools"} <= resource_uris

            prompts = await session.list_prompts()
            prompt_names = {prompt.name for prompt in prompts.prompts}
            assert {"tutor", "algorithm_coach", "interviewer", "quiz", "interview"} <= prompt_names

    anyio.run(exercise)


def test_mcp_server_calls_score_jd_skill_fit_tool():
    async def exercise() -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            result = await session.call_tool(
                "score_jd_skill_fit",
                {
                    "target_role": "AI Agent",
                    "skills": [
                        {"name": "Python", "jd_importance": 5, "user_level": 4},
                        {"name": "RAG", "jd_importance": 5, "user_level": 1},
                    ],
                },
            )
            assert result.isError is False
            assert result.structuredContent["ok"] is True
            assert result.structuredContent["fit_score"] == 50

    anyio.run(exercise)


def test_sync_business_tool_does_not_block_mcp_event_loop(monkeypatch):
    def slow_score_jd_skill_fit(*, skills, target_role=None):
        time.sleep(0.15)
        return {"ok": True, "fit_score": 100, "target_role": target_role}

    monkeypatch.setattr(mcp_tools, "tool_score_jd_skill_fit", slow_score_jd_skill_fit)

    async def exercise() -> None:
        completed = anyio.Event()

        async with create_connected_server_and_client_session(mcp) as session:
            async def call_tool() -> None:
                result = await session.call_tool(
                    "score_jd_skill_fit",
                    {"target_role": "AI Agent", "skills": []},
                )
                assert result.isError is False
                completed.set()

            async with anyio.create_task_group() as task_group:
                task_group.start_soon(call_tool)
                await anyio.sleep(0.02)
                assert not completed.is_set()

    anyio.run(exercise)


def test_stdio_launcher_can_import_app_when_run_directly(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_mcp_server.py"
    env = dict(os.environ)
    env["MCP_SERVER_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "MCP_SERVER_ENABLED=true is required" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
