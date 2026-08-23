"""RAG 三态在 /chat 与 /chat/stream API 层的端到端契约测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.db import database
from app.main import app
from app.repositories.session_repository import create_session
from app.schemas.chat import Source, ToolTrace


client = TestClient(app)


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def model_reply(answer, source_ids=None):
    """新契约：模型输出就是 Markdown 正文，不再有 source_ids 字段。"""

    return answer


def configure_chat_service(monkeypatch, raw_reply, ledger=None):
    """替掉 orchestrator.run，捕获三态参数并返回固定回复与账本。"""

    service = chat_route.tutor_agent_service
    monkeypatch.setattr(service, "seed_context_enabled", False)
    captured: dict = {}

    def fake_run(messages, **kwargs):
        captured["messages"] = messages
        captured.update(kwargs)
        return raw_reply, ToolTrace(
            used=bool(ledger),
            calls=[],
            ledger=dict(ledger or {}),
        )

    monkeypatch.setattr(service.react_orchestrator, "run", fake_run)
    return captured


def note_source(note_id="note_1"):
    return Source(
        id=note_id,
        title="docs/backend/fastapi.md · FastAPI 依赖注入",
        url="",
        domain="knowledge_note",
    )


def test_old_request_without_rag_fields_stays_in_auto_mode(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    captured = configure_chat_service(
        monkeypatch,
        model_reply("ordinary answer"),
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "ordinary question",
        },
    )

    assert response.status_code == 200
    assert captured["rag_enabled"] is True
    assert captured["force_rag"] is False


def test_force_rag_request_is_forwarded_to_orchestrator(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    captured = configure_chat_service(
        monkeypatch,
        model_reply("answer with note [note_1]"),
        ledger={"note_1": note_source()},
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "FastAPI 依赖注入",
            "rag_enabled": True,
            "force_rag": True,
        },
    )

    assert response.status_code == 200
    assert captured["rag_enabled"] is True
    assert captured["force_rag"] is True
    assert response.json()["reply"]["sources"][0]["domain"] == "knowledge_note"


def test_rag_disabled_request_forwarded_without_force(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    captured = configure_chat_service(
        monkeypatch,
        model_reply("plain answer"),
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "question",
            "rag_enabled": False,
            "force_rag": False,
        },
    )

    assert response.status_code == 200
    assert captured["rag_enabled"] is False
    assert captured["force_rag"] is False


def test_invalid_force_rag_without_rag_enabled_returns_422(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "message": "question",
            "rag_enabled": False,
            "force_rag": True,
        },
    )

    assert response.status_code == 422


def test_fake_note_reference_is_filtered_out(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    configure_chat_service(
        monkeypatch,
        model_reply(
            "回答引用 [note_1] 与伪造的 [note_999]。",
            ["note_1", "note_999"],
        ),
        ledger={"note_1": note_source()},
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "question",
            "rag_enabled": True,
            "force_rag": True,
        },
    )

    reply = response.json()["reply"]
    assert "[note_1]" in reply["answer"]
    assert "[note_999]" not in reply["answer"]
    assert [source["id"] for source in reply["sources"]] == ["note_1"]


def test_web_attachment_and_note_sources_can_share_one_ledger(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    ledger = {
        "note_1": note_source(),
        "web_1": Source(
            id="web_1",
            title="Web A",
            url="https://example.com/a",
            domain="example.com",
        ),
        "attachment_1": Source(
            id="attachment_1",
            title="resume.pdf · 第 2 页",
            url="",
            domain="attachment",
        ),
    }
    configure_chat_service(
        monkeypatch,
        model_reply(
            "本地 [note_1]、网页 [web_1] 与附件 [attachment_1]。",
            ["note_1", "web_1", "attachment_1"],
        ),
        ledger=ledger,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "question",
            "rag_enabled": True,
            "force_rag": True,
        },
    )

    reply = response.json()["reply"]
    assert [source["id"] for source in reply["sources"]] == [
        "note_1",
        "web_1",
        "attachment_1",
    ]
    assert reply["sources"][0]["url"] == ""
    assert reply["sources"][0]["domain"] == "knowledge_note"


def test_rag_disabled_rejects_note_references_even_if_model_claims_them(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    configure_chat_service(
        monkeypatch,
        model_reply("即使关闭也写了 [note_1]。", ["note_1"]),
        ledger={"note_1": note_source()},
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "question",
            "rag_enabled": False,
            "force_rag": False,
        },
    )

    reply = response.json()["reply"]
    assert "[note_1]" not in reply["answer"]
    assert reply["sources"] == []


def test_no_hit_force_rag_returns_no_sources(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    configure_chat_service(
        monkeypatch,
        model_reply("知识库未找到与当前问题足够相关的资料。", []),
        ledger={},
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "private plan question",
            "rag_enabled": True,
            "force_rag": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"]["sources"] == []


def test_stream_force_rag_passes_three_state_and_returns_note_sources(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = chat_route.tutor_agent_service
    monkeypatch.setattr(service, "seed_context_enabled", False)
    captured: dict = {}

    def fake_run_stream(messages, **kwargs):
        captured["messages"] = messages
        captured.update(kwargs)
        yield SimpleNamespace(type="token", data={"text": "基于 [note_1] 的回答。"})
        return (
            "基于 [note_1] 的回答。",
            ToolTrace(used=True, ledger={"note_1": note_source()}),
        )

    monkeypatch.setattr(service.react_orchestrator, "run_stream", fake_run_stream)

    response = client.post(
        "/chat/stream",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "FastAPI 依赖注入",
            "rag_enabled": True,
            "force_rag": True,
        },
    )

    assert response.status_code == 200
    assert captured["rag_enabled"] is True
    assert captured["force_rag"] is True
    events = response.text.strip().split("\n\n")
    done_event = next(
        json.loads(block.splitlines()[-1][6:])
        for block in events
        if "event: done" in block
    )
    assert done_event["reply"]["sources"][0]["domain"] == "knowledge_note"
