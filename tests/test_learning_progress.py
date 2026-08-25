"""学习进度 API 和共享 Service 的测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.learning_progress_service import LearningProgressService


client = TestClient(app)


def test_learning_progress_can_be_created_and_updated_without_duplicates():
    created = client.put(
        "/learning-progress",
        json={
            "user_id": "alice",
            "subject": "SQL",
            "topic": "  LEFT   JOIN ",
            "level": 1,
            "status": "needs_practice",
            "evidence": "容易忘记连接条件",
            "next_step": "完成两道 LEFT JOIN 练习",
        },
    )

    assert created.status_code == 200
    assert created.json()["topic"] == "LEFT JOIN"
    assert created.json()["subject"] == "sql"
    assert created.json()["source"] == "manual"

    updated = client.put(
        "/learning-progress",
        json={
            "user_id": "alice",
            "subject": "sql",
            "topic": "LEFT JOIN",
            "level": 2,
            "status": "learning",
            "evidence": "已经能够写出基础连接",
            "next_step": "练习 ON 和 WHERE 的区别",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["level"] == 2

    listed = client.get("/learning-progress?user_id=alice&subject=sql")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["evidence"] == "已经能够写出基础连接"


def test_learning_progress_isolated_by_user_and_subject():
    client.put(
        "/learning-progress",
        json={
            "user_id": "alice",
            "subject": "sql",
            "topic": "SELECT",
            "level": 3,
            "status": "mastered",
        },
    )

    assert client.get("/learning-progress?user_id=alice&subject=sql").json()["items"]
    assert client.get("/learning-progress?user_id=bob&subject=sql").json()["items"] == []
    assert client.get("/learning-progress?user_id=alice&subject=python").json()["items"] == []


def test_learning_progress_validates_level():
    response = client.put(
        "/learning-progress",
        json={
            "user_id": "alice",
            "subject": "sql",
            "topic": "GROUP BY",
            "level": 4,
            "status": "learning",
        },
    )

    assert response.status_code == 422


def test_shared_service_supports_agent_source_for_next_phase():
    record = LearningProgressService().save_agent(
        user_id="alice",
        subject="sql",
        topic="NULL",
        level=1,
        status="needs_practice",
        evidence="把 NULL 当成了普通字符串比较",
        next_step="练习 IS NULL 和 IS NOT NULL",
    )

    assert record.source.value == "agent"
    assert record.status.value == "needs_practice"
