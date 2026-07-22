"""Tests for Tutor Agent MCP server primitives."""
from __future__ import annotations
import anyio
from mcp.shared.memory import create_connected_server_and_client_session
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
