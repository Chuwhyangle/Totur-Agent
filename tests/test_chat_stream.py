"""SSE chat route contract tests."""

import json
from contextvars import copy_context
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.main import app
from app.services.agent.react_orchestrator import ReactOrchestrator, StreamEvent


client = TestClient(app)
REQUEST = {"user_id": "stream-user", "message": "explain SSE"}


def _parse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n") if body.strip() else []:
        lines = block.splitlines()
        event_type = next(line[7:] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        events.append((event_type, data))
    return events


def test_stream_preserves_token_tool_and_done_event_order(monkeypatch):
    final_reply = {
        "answer": "hello world",
        "sources": [],
    }

    def fake_stream(_request):
        yield {"event": "token", "data": {"text": "hello "}}
        yield {"event": "tool_call", "data": {"tool": "search", "args": {"q": "SSE"}}}
        yield {"event": "tool_result", "data": {"tool": "search", "result": {"ok": True}}}
        yield {"event": "token", "data": {"text": "world"}}
        yield {
            "event": "done",
            "data": {"full_response": "hello world", "reply": final_reply, "session_id": 7},
        }

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", fake_stream)

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = _parse_events(response.text)
    assert [event_type for event_type, _ in events] == [
        "token", "tool_call", "tool_result", "token", "done"
    ]
    assert "".join(data["text"] for kind, data in events if kind == "token") == "hello world"
    assert events[-1][1]["reply"] == final_reply


def test_stream_serializes_multiple_model_chunks_as_multiple_sse_token_events(monkeypatch):
    """多个模型 chunk 应经服务事件转换为多个 SSE token 事件。"""

    from types import SimpleNamespace

    from app.services.agent.react_orchestrator import ReactOrchestrator

    class Chunks:
        def __iter__(self):
            return iter([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="第一"))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="部分"))]),
            ])

    orchestrator = ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: Chunks()),
            ),
        ),
    )

    def fake_stream(_request):
        stream = orchestrator._stream_round([])
        for event in stream:
            yield {"event": event.type, "data": event.data}
        yield {
            "event": "done",
            "data": {"full_response": "第一部分", "reply": {}, "session_id": 7},
        }

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", fake_stream)

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    events = _parse_events(response.text)
    assert [event_type for event_type, _ in events] == ["token", "token", "done"]
    assert [data["text"] for kind, data in events if kind == "token"] == [
        "第一",
        "部分",
    ]


def test_stream_converts_generator_exception_to_well_formed_error_event(monkeypatch):
    def broken_stream(_request):
        yield {"event": "token", "data": {"text": "partial"}}
        raise RuntimeError("model stream failed")

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", broken_stream)

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    assert _parse_events(response.text) == [
        ("token", {"text": "partial"}),
        (
            "error",
            {
                "error": "stream_internal_error",
                "stage": "stream",
                "message": "流式响应处理失败，请重试。",
                "debug_message": "RuntimeError: model stream failed",
                "retryable": True,
            },
        ),
    ]


def test_stream_converts_missing_terminal_event_to_error(monkeypatch):
    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", lambda _request: iter(()))

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    assert _parse_events(response.text) == [
        ("error", {"message": "Stream ended before completion"}),
    ]


def test_stream_handles_generator_that_ends_after_one_token(monkeypatch):
    def early_stream(_request):
        yield {"event": "token", "data": {"text": "only"}}

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", early_stream)

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    assert _parse_events(response.text) == [
        ("token", {"text": "only"}),
        ("error", {"message": "Stream ended before completion"}),
    ]


def test_stream_context_switch_finishes_with_one_done_event(monkeypatch):
    orchestrator = ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(),
    )
    model_spec = SimpleNamespace(model_id="model-a")

    def fake_stream_round(messages, **kwargs):
        yield StreamEvent(type="token", data={"text": "hello"})
        yield StreamEvent(type="token", data={"text": " world"})
        return SimpleNamespace(
            content="hello world",
            reasoning="",
            tool_calls=[],
        )

    orchestrator._stream_round = fake_stream_round

    def fake_stream(_request):
        stream = orchestrator.run_stream(
            [],
            model_spec=model_spec,
            execution_context=object(),
        )
        context_a = copy_context()
        context_b = copy_context()
        first_event = context_a.run(next, stream)
        yield {"event": first_event.type, "data": first_event.data}
        while True:
            try:
                event = context_b.run(next, stream)
            except StopIteration as stop:
                raw_reply, _tool_trace = stop.value
                yield {
                    "event": "done",
                    "data": {
                        "full_response": raw_reply,
                        "reply": {"answer": raw_reply, "sources": []},
                    },
                }
                return
            yield {"event": event.type, "data": event.data}

    monkeypatch.setattr(chat_route.tutor_agent_service, "chat_stream", fake_stream)

    response = client.post("/chat/stream", json=REQUEST)

    assert response.status_code == 200
    events = _parse_events(response.text)
    assert [event_type for event_type, _ in events] == ["token", "token", "done"]
    assert events[-1][1]["reply"]["answer"] == "hello world"
