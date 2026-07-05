"""Tests for the Tutor Agent tool registry and executor."""

from app.db import database
from app.repositories.interview_jd_repository import create_interview_jd
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.agent.tools.score_jd_skill_fit import score_jd_skill_fit


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def test_tool_registry_exposes_interview_jd_search_schema():
    registry = ToolRegistry()

    tools = registry.get_tools_schema()
    tool = next(tool for tool in tools if tool["function"]["name"] == "interview_jd_search")
    parameters = tool["function"]["parameters"]

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "interview_jd_search"
    assert set(parameters["properties"]) == {"query", "limit"}
    assert parameters["required"] == ["query"]
    assert "id" not in parameters["properties"]


def test_tool_registry_exposes_score_jd_skill_fit_schema():
    registry = ToolRegistry()

    tools = registry.get_tools_schema()
    names = [tool["function"]["name"] for tool in tools]
    tool = next(tool for tool in tools if tool["function"]["name"] == "score_jd_skill_fit")
    parameters = tool["function"]["parameters"]
    skill_properties = parameters["properties"]["skills"]["items"]["properties"]

    assert names == ["interview_jd_search", "score_jd_skill_fit"]
    assert tool["type"] == "function"
    assert set(parameters["properties"]) == {"target_role", "skills"}
    assert parameters["required"] == ["skills"]
    assert set(skill_properties) == {
        "name",
        "jd_importance",
        "user_level",
        "confidence",
        "evidence",
        "reason",
        "recommended_action",
    }


def test_score_jd_skill_fit_calculates_weighted_fit_score():
    result = score_jd_skill_fit(
        target_role="AI Agent / LLM 应用开发",
        skills=[
            {
                "name": "Python",
                "jd_importance": 5,
                "user_level": 4,
                "confidence": "high",
                "evidence": "做过 FastAPI 后端。",
            },
            {
                "name": "RAG",
                "jd_importance": 5,
                "user_level": 1,
                "confidence": "high",
            },
            {
                "name": "Function Calling",
                "jd_importance": 4,
                "user_level": 3,
                "confidence": "medium",
            },
        ],
    )

    assert result["ok"] is True
    assert result["target_role"] == "AI Agent / LLM 应用开发"
    assert result["fit_score"] == 53
    assert result["fit_level"] == "partial_fit"
    assert result["max_score"] == 100
    assert result["top_strengths"] == ["Python"]
    assert result["top_gaps"] == ["RAG"]
    assert result["uncertain_skills"] == ["Function Calling"]
    assert result["summary"] == {
        "skill_count": 3,
        "high_importance_gap_count": 1,
        "uncertain_skill_count": 1,
    }
    assert result["skill_scores"][1] == {
        "name": "RAG",
        "jd_importance": 5,
        "user_level": 1,
        "confidence": "high",
        "weighted_score": 5,
        "weighted_max": 25,
        "gap": 4,
        "weighted_gap": 20,
        "evidence": "",
        "reason": "",
        "recommended_action": "",
    }


def test_score_jd_skill_fit_clamps_scores_and_normalizes_confidence():
    result = score_jd_skill_fit(
        skills=[
            {
                "name": "Python",
                "jd_importance": 9,
                "user_level": 8,
                "confidence": "certain",
            },
            {
                "name": "RAG",
                "jd_importance": -1,
                "user_level": -2,
                "confidence": "low",
            },
        ],
    )

    assert result["ok"] is True
    assert result["fit_score"] == 83
    assert result["skill_scores"][0]["jd_importance"] == 5
    assert result["skill_scores"][0]["user_level"] == 5
    assert result["skill_scores"][0]["confidence"] == "medium"
    assert result["skill_scores"][1]["jd_importance"] == 1
    assert result["skill_scores"][1]["user_level"] == 0
    assert result["uncertain_skills"] == ["Python", "RAG"]


def test_score_jd_skill_fit_rejects_empty_skills():
    result = score_jd_skill_fit(skills=[])

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "skills must be a non-empty list.",
    }


def test_score_jd_skill_fit_rejects_skill_without_name():
    result = score_jd_skill_fit(skills=[{"jd_importance": 5, "user_level": 4}])

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "each skill must include a non-empty name.",
    }


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


def test_tool_executor_runs_score_jd_skill_fit():
    executor = ToolExecutor()

    result = executor.execute(
        "score_jd_skill_fit",
        {
            "target_role": "AI Agent",
            "skills": [
                {"name": "Python", "jd_importance": 5, "user_level": 4},
                {"name": "RAG", "jd_importance": 5, "user_level": 1},
            ],
        },
    )

    assert result["ok"] is True
    assert result["target_role"] == "AI Agent"
    assert result["fit_score"] == 50
    assert result["top_gaps"] == ["RAG"]


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
