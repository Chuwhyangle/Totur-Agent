"""FR-3: 附件工具化 + tool_choice 强制的 API 与编排测试。

附件从「预注入上下文」改为「search_attachments 工具 + tool_choice 强制」。
"""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes import chat as chat_route
from app.db import database
from app.main import app
from app.repositories.session_repository import create_session
from app.schemas.chat import ChatRequest, Source, ToolTrace
from app.services.documents.attachment_retrieval_service import (
    AttachmentEvidence,
    AttachmentNoRelevantEvidenceError,
)


client = TestClient(app)


class FakeAttachmentRetrievalService:
    """替身：记录 retrieve 调用，返回配置好的 evidence 或抛错。"""

    context_max_chars = 8000

    def __init__(self, evidence=None, error=None):
        self.evidence = list(evidence or [])
        self.error = error
        self.calls = []

    def retrieve(self, user_id, session_id, attachment_ids, query):
        self.calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "attachment_ids": list(attachment_ids),
                "query": query,
            }
        )
        if self.error is not None:
            raise self.error
        return list(self.evidence)


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "chat-attachments.db")


def model_reply(answer, source_ids=None):
    return json.dumps(
        {
            "answer": answer,
            "next_task": "next",
            "exercise": "exercise",
            "checkpoints": ["one", "two", "three"],
            "source_ids": source_ids or [],
        },
        ensure_ascii=False,
    )


def configure_chat_service(
    monkeypatch,
    retrieval_service,
    raw_reply,
    *,
    tool_calls=None,
):
    """把 orchestrator 的 run 替换为 fake，注入附件检索服务。

    tool_calls：模拟模型的工具调用序列（list of dict）。
    默认无工具调用，直接返回 raw_reply。
    """

    service = chat_route.tutor_agent_service
    monkeypatch.setattr(service, "seed_context_enabled", False)
    monkeypatch.setattr(
        service,
        "attachment_retrieval_service",
        retrieval_service,
    )
    captured_messages = []

    def fake_run(messages, **kwargs):
        captured_messages.extend(messages)
        return raw_reply, ToolTrace(used=bool(tool_calls), calls=tool_calls or [])

    monkeypatch.setattr(service.react_orchestrator, "run", fake_run)
    return captured_messages


def evidence(text="Resume evidence", evidence_id="attachment_1"):
    return AttachmentEvidence(
        evidence_id=evidence_id,
        document_id="server-document-id",
        original_filename="resume.pdf",
        page_start=2,
        page_end=2,
        text=text,
        similarity=0.91,
    )


def test_chat_request_deduplicates_attachment_ids_and_rejects_invalid_values():
    request = ChatRequest(
        user_id="alice",
        message="question",
        attachment_ids=[" doc-1 ", "doc-1", "doc-2"],
    )

    assert request.attachment_ids == ["doc-1", "doc-2"]

    with pytest.raises(ValidationError):
        ChatRequest(
            user_id="alice",
            message="question",
            attachment_ids=[""],
        )
    with pytest.raises(ValidationError):
        ChatRequest(
            user_id="alice",
            message="question",
            attachment_ids=None,
        )
    with pytest.raises(ValidationError):
        ChatRequest(
            user_id="alice",
            message="question",
            attachment_ids=[f"doc-{index}" for index in range(6)],
        )


def test_chat_without_attachment_ids_does_not_touch_attachment_service(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    retrieval = FakeAttachmentRetrievalService(error=AssertionError("must not run"))
    captured = configure_chat_service(
        monkeypatch,
        retrieval,
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
    assert retrieval.calls == []
    assert [item["role"] for item in captured] == ["system", "user"]
    assert captured[-1]["content"] == "ordinary question"


def test_chat_with_attachment_ids_forces_search_attachments_tool(
    monkeypatch,
    tmp_path,
):
    """FR-3 验收：attachment_ids 非空时，附件服务被注入到工具默认参数。"""

    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    retrieval = FakeAttachmentRetrievalService([evidence("Resume evidence")])
    configure_chat_service(
        monkeypatch,
        retrieval,
        model_reply("answer"),
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "Summarize my resume",
            "attachment_ids": ["server-document-id"],
        },
    )

    assert response.status_code == 200
    # 附件服务已注入，但未在 service 层预检索（由工具在 ReAct 内调用）。
    assert retrieval.calls == []


def test_search_attachments_tool_passes_request_context_to_service(
    monkeypatch,
    tmp_path,
):
    """search_attachments 工具把 user/session/attachment 传给检索服务。"""

    from app.services.agent.tools.search_attachments import search_attachments

    retrieval = FakeAttachmentRetrievalService([evidence("Resume evidence")])
    result = search_attachments(
        query="Summarize my resume",
        attachment_retrieval_service=retrieval,
        user_id="alice",
        session_id=11,
        attachment_ids=["server-document-id"],
    )

    assert result["ok"] is True
    assert result["found"] is True
    assert result["items"][0]["evidence_id"] == "attachment_1"
    assert result["items"][0]["title"] == "resume.pdf · 第 2 页"
    assert retrieval.calls[0]["user_id"] == "alice"
    assert retrieval.calls[0]["session_id"] == 11
    assert retrieval.calls[0]["attachment_ids"] == ["server-document-id"]
    assert retrieval.calls[0]["query"] == "Summarize my resume"


def test_search_attachments_tool_returns_stable_error_envelope(
    monkeypatch,
    tmp_path,
):
    """附件检索失败时返回 {ok:false, error, message} 信封，不泄漏内部路径。"""

    from app.services.agent.tools.search_attachments import search_attachments

    retrieval = FakeAttachmentRetrievalService(
        error=AttachmentNoRelevantEvidenceError()
    )
    result = search_attachments(
        query="question",
        attachment_retrieval_service=retrieval,
        user_id="alice",
        session_id=11,
        attachment_ids=["doc-1"],
    )

    # 无相关证据 → ok:true, found:false（不是错误）
    assert result["ok"] is True
    assert result["found"] is False
    assert "没有检索到" in result["message"]


def test_search_attachments_tool_requires_request_context():
    """缺少 user/session/attachment 时返回明确错误（权限参数不进 schema 的兜底）。"""

    from app.services.agent.tools.search_attachments import search_attachments

    result = search_attachments(query="question")

    assert result["ok"] is False
    assert result["error"] == "missing_request_context"


def test_search_attachments_tool_rejects_empty_query():
    from app.services.agent.tools.search_attachments import search_attachments

    result = search_attachments(query="   ")

    assert result["ok"] is False
    assert result["error"] == "invalid_arguments"


def test_react_orchestrator_forces_attachment_tool_choice_first_round(
    monkeypatch,
    tmp_path,
):
    """FR-3 核心：attachment_ids 非空时首轮 tool_choice 强制 search_attachments。"""

    from types import SimpleNamespace

    from app.services.agent.react_orchestrator import ReactOrchestrator

    registry = SimpleNamespace(
        get_tools_schema=lambda: [],
        has_tool=lambda name: True,
        is_external_tool=lambda name: False,
        get_tool=lambda name: None,
    )
    orchestrator = ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(),
        tool_registry=registry,
    )
    # 直接验证 _resolve_tool_choice
    run_state = SimpleNamespace(attachment_ids=["doc-1"])
    choice = orchestrator._resolve_tool_choice(run_state, round_number=1)
    assert choice == {
        "type": "function",
        "function": {"name": "search_attachments"},
    }
    # 非首轮或没有附件 → auto
    assert orchestrator._resolve_tool_choice(run_state, round_number=2) == "auto"
    no_attachment = SimpleNamespace(attachment_ids=[])
    assert orchestrator._resolve_tool_choice(no_attachment, round_number=1) == "auto"


def test_react_orchestrator_prepares_attachment_ledger(monkeypatch, tmp_path):
    """_prepare_attachment_result 把附件项写入 ledger 并保持引用契约。"""

    from types import SimpleNamespace

    from app.services.agent.react_orchestrator import ReactOrchestrator

    orchestrator = ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(),
        tool_registry=SimpleNamespace(
            get_tools_schema=lambda: [],
            has_tool=lambda name: True,
            is_external_tool=lambda name: False,
            get_tool=lambda name: None,
        ),
    )
    run_state = SimpleNamespace(ledger={})
    tool_result = {
        "ok": True,
        "items": [
            {
                "evidence_id": "attachment_1",
                "title": "resume.pdf · 第 2 页",
                "content": "Resume evidence",
                "similarity": 0.91,
            }
        ],
        "summary": {"returned_count": 1},
    }
    prepared = orchestrator._prepare_attachment_result(tool_result, run_state)

    assert prepared["items"][0]["evidence_id"] == "attachment_1"
    assert "attachment_1" in run_state.ledger
    assert run_state.ledger["attachment_1"].domain == "attachment"
    assert run_state.ledger["attachment_1"].title == "resume.pdf · 第 2 页"