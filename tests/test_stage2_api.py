from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_service_status():
    """阶段 2 验收：健康检查接口应该返回服务状态。"""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "tutor-agent-api",
    }


def test_chat_returns_placeholder_reply():
    """阶段 2 验收：/chat 先接收 JSON，并返回固定占位回复。"""
    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "FastAPI 的路由是什么？",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "default"
    assert body["message"] == "FastAPI 的路由是什么？"
    assert body["reply"]["answer"] == "这是阶段 2 的固定占位回复。"
    assert body["reply"]["next_task"] == "下一步会把这里接入阶段 1 的模型调用逻辑。"
