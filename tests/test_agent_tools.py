"""Tests for the Tutor Agent tool registry and executor."""

from app.db import database
from app.repositories.interview_jd_repository import create_interview_jd
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def test_tool_registry_exposes_interview_jd_search_schema():
    registry = ToolRegistry()

    tools = registry.get_tools_schema()
    tool = tools[0]
    parameters = tool["function"]["parameters"]

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "interview_jd_search"
    assert set(parameters["properties"]) == {"query", "limit"}
    assert parameters["required"] == ["query"]
    assert "id" not in parameters["properties"]


def test_tool_executor_runs_interview_jd_search(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_interview_jd(
        user_id="demo-user",
        title="Python AI Agent 开发工程师",
        raw_text="负责 Agent 工具调用和 RAG 应用开发。",
        core_skills=["Function Calling", "RAG"],
        keywords=["Agent", "RAG"],
        interview_focus=["Agent 工具调用"],
    )
    executor = ToolExecutor()

    result = executor.execute(
        "interview_jd_search",
        {"query": "Agent RAG", "limit": 1},
    )

    assert result["ok"] is True
    assert result["items"][0]["title"] == "Python AI Agent 开发工程师"


def test_tool_executor_accepts_json_string_arguments(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_interview_jd(
        user_id="demo-user",
        title="AI 全栈开发工程师",
        raw_text="负责 Vue 和 Python AI 应用开发。",
        keywords=["Vue", "Python", "AI 全栈"],
    )
    executor = ToolExecutor()

    result = executor.execute(
        "interview_jd_search",
        '{"query": "Vue 全栈", "limit": 1}',
    )

    assert result["ok"] is True
    assert result["items"][0]["title"] == "AI 全栈开发工程师"


def test_tool_executor_returns_structured_error_for_unknown_tool():
    executor = ToolExecutor()

    result = executor.execute("unknown_tool", {"query": "Agent"})

    assert result == {
        "ok": False,
        "error": "tool_not_found",
        "message": "unknown tool: unknown_tool",
    }


def test_tool_executor_returns_structured_error_for_invalid_arguments():
    executor = ToolExecutor()

    result = executor.execute("interview_jd_search", "{bad json")

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "tool arguments must be a JSON object.",
    }
