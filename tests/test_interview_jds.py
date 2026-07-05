"""Interview JD storage tests.

These tests describe the first foundation for target-job storage. Tool search
will come later; this layer only saves and lists user-provided JD records.
"""

import sqlite3

from fastapi.testclient import TestClient

from app.db import database
from app.db.models import INTERVIEW_JDS_TABLE
from app.main import app
from app.repositories.interview_jd_repository import (
    create_interview_jd,
    list_interview_jds,
)


client = TestClient(app)


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def sample_jd_payload(user_id: str = "demo-user") -> dict:
    return {
        "user_id": user_id,
        "title": "AI Agent / LLM 应用开发岗位",
        "role_family": "ai_agent_engineer",
        "seniority": "graduate",
        "target_graduation_years": ["2025", "2026"],
        "raw_text": "基于大语言模型开发智能 Agent 应用，实现自动化任务处理。",
        "responsibilities": [
            "基于大语言模型开发智能 Agent 应用，实现自动化任务处理",
            "设计和实现 RAG 系统，提升 AI 回答的准确性和相关性",
        ],
        "must_have": ["Python 编程基础", "机器学习基础概念"],
        "core_skills": ["LangChain", "LangGraph"],
        "preferred_skills": ["RAG", "Agent 评测"],
        "bonus_skills": ["FastAPI", "Docker", "Git"],
        "keywords": ["LLM", "Agent", "RAG", "FastAPI"],
        "interview_focus": ["Agent 工具调用", "RAG 系统设计"],
    }


def test_initialize_database_creates_interview_jds_table(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    database.initialize_database()

    connection = sqlite3.connect(database.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({INTERVIEW_JDS_TABLE})")
        }
    finally:
        connection.close()

    assert {
        "id",
        "user_id",
        "title",
        "raw_text",
        "core_skills_json",
        "interview_focus_json",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_create_and_list_interview_jds(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    payload = sample_jd_payload()
    created = create_interview_jd(**payload)
    list_for_demo_user = list_interview_jds("demo-user")
    list_for_other_user = list_interview_jds("other-user")

    assert created.id > 0
    assert created.user_id == "demo-user"
    assert created.title == "AI Agent / LLM 应用开发岗位"
    assert created.core_skills == ["LangChain", "LangGraph"]
    assert created.interview_focus == ["Agent 工具调用", "RAG 系统设计"]
    assert [record.id for record in list_for_demo_user] == [created.id]
    assert list_for_other_user == []


def test_post_interview_jds_creates_record(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    response = client.post("/interview-jds", json=sample_jd_payload("alice"))

    assert response.status_code == 201
    body = response.json()

    assert body["id"] > 0
    assert body["user_id"] == "alice"
    assert body["title"] == "AI Agent / LLM 应用开发岗位"
    assert body["core_skills"] == ["LangChain", "LangGraph"]
    assert body["keywords"] == ["LLM", "Agent", "RAG", "FastAPI"]


def test_get_interview_jds_returns_current_user_records(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    first = create_interview_jd(**sample_jd_payload("alice"))
    second_payload = sample_jd_payload("alice")
    second_payload["title"] = "后端 AI 应用岗位"
    second = create_interview_jd(**second_payload)
    create_interview_jd(**sample_jd_payload("bob"))

    response = client.get("/interview-jds?user_id=alice")

    assert response.status_code == 200
    body = response.json()

    assert body["user_id"] == "alice"
    assert [item["id"] for item in body["items"]] == [second.id, first.id]
    assert [item["title"] for item in body["items"]] == [
        "后端 AI 应用岗位",
        "AI Agent / LLM 应用开发岗位",
    ]


def test_interview_jds_reject_empty_raw_text():
    response = client.post(
        "/interview-jds",
        json={
            **sample_jd_payload("alice"),
            "raw_text": "",
        },
    )

    assert response.status_code == 422

