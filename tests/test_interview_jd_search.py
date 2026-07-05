"""Tests for the first interview JD search tool."""

from app.db import database
from app.repositories.interview_jd_repository import create_interview_jd
from app.services.agent.tools.interview_jd_search import search_interview_jds


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def create_agent_jd():
    return create_interview_jd(
        user_id="demo-user",
        title="Python AI Agent 开发工程师",
        role_family="python_ai_agent_engineer",
        seniority="junior_mid",
        raw_text="负责基于 LLM 的 AI Agent 开发，构建具备工具调用和 RAG 能力的智能应用。",
        responsibilities=["基于 LLM 开发 AI Agent", "封装 Function Calling 工具接口"],
        must_have=["Python 编程能力", "大模型 API 调用经验"],
        core_skills=["Python", "LLM API", "Function Calling", "RAG"],
        preferred_skills=["MCP", "A2A"],
        bonus_skills=["NetOps/AIOps"],
        keywords=["Python", "Agent", "LLM", "Function Calling", "RAG"],
        interview_focus=["Agent 工具调用流程", "RAG 基本架构"],
    )


def create_fullstack_jd():
    return create_interview_jd(
        user_id="demo-user",
        title="AI 全栈开发工程师",
        role_family="ai_fullstack_engineer",
        seniority="graduate",
        raw_text="负责 Java/Python/Vue 的系统服务与 AI 应用开发。",
        responsibilities=["前后端一体化开发", "AI 应用开发"],
        must_have=["算法数据结构", "Web API 设计"],
        core_skills=["Java", "Python", "Vue", "数据库"],
        preferred_skills=["AI 开发工具", "系统架构"],
        bonus_skills=["Cursor", "Claude Code"],
        keywords=["AI 全栈", "Vue", "Java", "Python"],
        interview_focus=["Web 架构", "API 设计", "AI 工具协作"],
    )


def test_search_interview_jds_finds_agent_jd_without_exposing_database_id(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    create_fullstack_jd()
    create_agent_jd()

    result = search_interview_jds("Agent 工具调用 RAG 面试", limit=3)

    assert result["ok"] is True
    assert result["summary"]["searched_count"] == 2
    assert result["items"][0]["title"] == "Python AI Agent 开发工程师"
    assert result["items"][0]["match_score"] > 0
    assert "id" not in result["items"][0]
    assert "raw_text_excerpt" in result["items"][0]
    assert {
        "core_skills",
        "keywords",
        "interview_focus",
    }.intersection(result["items"][0]["matched_fields"])


def test_search_interview_jds_respects_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_agent_jd()
    create_fullstack_jd()

    result = search_interview_jds("AI Python", limit=1)

    assert result["ok"] is True
    assert result["summary"]["returned_count"] == 1
    assert len(result["items"]) == 1


def test_search_interview_jds_returns_empty_items_for_no_match(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_agent_jd()

    result = search_interview_jds("量子通信产品经理", limit=3)

    assert result["ok"] is True
    assert result["items"] == []
    assert result["summary"] == {
        "returned_count": 0,
        "searched_count": 1,
    }
    assert result["message"] == "No interview JD matched the query."


def test_search_interview_jds_rejects_empty_query(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    result = search_interview_jds("   ", limit=3)

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "query must be a non-empty string.",
    }
