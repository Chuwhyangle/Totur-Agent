"""Trace lifecycle tests for non-streaming and streaming chat services."""

from types import SimpleNamespace

import pytest

from app.schemas.chat import ChatRequest, ToolTrace, TutorReply
from app.services import timings
from app.services.agent.react_orchestrator import StreamEvent
from app.services.tutor_agent_service import TutorAgentService
from app.db import trace_db


REQUEST = ChatRequest(user_id="trace-user", message="Explain queues")


def make_service(monkeypatch, *, run=None, run_stream=None):
    service = object.__new__(TutorAgentService)
    service.config = SimpleNamespace(model="test-model")
    service.seed_context_enabled = False
    service.seed_context_provider = lambda message: None
    service._resolve_session = lambda **kwargs: SimpleNamespace(
        id=7,
        persona_id="tutor",
        subject="",
        title="Existing session",
        workspace_id=None,
    )
    service.memory_manager = SimpleNamespace(
        load_context=lambda **kwargs: SimpleNamespace(recent_history=["prior"]),
        save_turn_and_update_summary=lambda **kwargs: None,
    )
    service.prompt_builder = SimpleNamespace(build_messages=lambda context, persona: [])
    service.tool_executor = SimpleNamespace(set_default_tool_kwargs=lambda value: None)
    service.response_parser = SimpleNamespace(
        parse_model_reply=lambda raw: TutorReply(
            answer=raw,
            next_task="next",
            exercise="exercise",
            checkpoints=[],
        )
    )
    service.react_orchestrator = SimpleNamespace(
        run=run or (lambda *args, **kwargs: ("answer", ToolTrace(used=False))),
        run_stream=run_stream
        or (lambda *args, **kwargs: iter(())),
    )
    return service


def capture_trace_calls(monkeypatch):
    calls = []

    def start_trace(**kwargs):
        calls.append(("start", kwargs))
        return kwargs["trace_id"]

    def finish_trace(**kwargs):
        calls.append(("finish", kwargs))
        return True

    monkeypatch.setattr(trace_db, "start_trace", start_trace)
    monkeypatch.setattr(trace_db, "finish_trace", finish_trace)
    return calls


def test_chat_success_finishes_one_trace_as_ok(monkeypatch):
    calls = capture_trace_calls(monkeypatch)
    service = make_service(monkeypatch)

    response = service.chat(REQUEST)

    assert response.session_id == 7
    assert [kind for kind, _ in calls] == ["start", "finish"]
    assert calls[0][1]["trace_id"] == calls[1][1]["trace_id"]
    assert calls[1][1]["status"] == "OK"


def test_chat_failure_finishes_one_trace_as_error(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    service = make_service(monkeypatch, run=fail)

    with pytest.raises(RuntimeError, match="model unavailable"):
        service.chat(REQUEST)

    assert [kind for kind, _ in calls] == ["start", "finish"]
    assert calls[1][1]["status"] == "ERROR"


def test_chat_stream_success_finishes_as_ok_without_protocol_changes(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def run_stream(*args, **kwargs):
        yield StreamEvent(type="token", data={"text": "answer"})
        return "answer", ToolTrace(used=False)

    service = make_service(monkeypatch, run_stream=run_stream)
    events = list(service.chat_stream(REQUEST))

    assert [event["event"] for event in events] == ["token", "done"]
    assert [kind for kind, _ in calls] == ["start", "finish"]
    assert calls[1][1]["status"] == "OK"


def test_chat_stream_model_exception_finishes_as_error(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def run_stream(*args, **kwargs):
        yield StreamEvent(type="token", data={"text": "partial"})
        raise RuntimeError("stream failed")

    service = make_service(monkeypatch, run_stream=run_stream)
    events = list(service.chat_stream(REQUEST))

    assert [event["event"] for event in events] == ["token", "error"]
    assert calls[1][1]["status"] == "ERROR"


def test_chat_stream_generator_close_finishes_as_cancelled(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def run_stream(*args, **kwargs):
        yield StreamEvent(type="token", data={"text": "partial"})
        yield StreamEvent(type="token", data={"text": "never sent"})

    service = make_service(monkeypatch, run_stream=run_stream)
    generator = service.chat_stream(REQUEST)

    first_event = next(generator)
    generator.close()

    assert first_event["event"] == "token"
    assert [kind for kind, _ in calls] == ["start", "finish"]
    assert calls[1][1]["status"] == "CANCELLED"


def test_chat_stream_persistence_failure_is_a_structured_business_error(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def run_stream(*args, **kwargs):
        if False:
            yield None
        return "answer", ToolTrace(used=False)

    service = make_service(monkeypatch, run_stream=run_stream)

    def fail_save(**_kwargs):
        raise RuntimeError("database is locked")

    service.memory_manager.save_turn_and_update_summary = fail_save
    events = list(service.chat_stream(REQUEST))

    assert [event["event"] for event in events] == ["error"]
    assert events[0]["data"] == {
        "error": "conversation_persistence_failed",
        "stage": "persistence",
        "message": "回答已生成，但对话保存失败。",
        "debug_message": "RuntimeError: database is locked",
        "retryable": True,
    }
    assert calls[1][1]["status"] == "ERROR"


def test_chat_stream_workspace_completion_failure_still_sends_done(monkeypatch):
    calls = capture_trace_calls(monkeypatch)

    def run_stream(*args, **kwargs):
        if False:
            yield None
        return "answer", ToolTrace(used=False)

    service = make_service(monkeypatch, run_stream=run_stream)

    def fail_completion(_context):
        raise RuntimeError("task update failed")

    service._complete_execution_context = fail_completion
    events = list(service.chat_stream(REQUEST))

    assert [event["event"] for event in events] == ["done"]
    assert events[0]["data"]["reply"]["answer"] == "answer"
    assert events[0]["data"]["warnings"] == [{
        "error": "workspace_task_completion_failed",
        "message": "回答已保存，但 Workspace Task 状态更新失败。",
        "debug_message": "RuntimeError: task update failed",
    }]
    assert calls[1][1]["status"] == "OK"


def test_stream_starts_request_timing_before_agent_work(monkeypatch):
    calls = capture_trace_calls(monkeypatch)
    observed = []

    def run_stream(*args, **kwargs):
        observed.append(timings.get_trace_id())
        return_value = ("answer", ToolTrace(used=False))
        if False:
            yield None
        return return_value

    service = make_service(monkeypatch, run_stream=run_stream)
    list(service.chat_stream(REQUEST))

    assert observed and observed[0] == calls[0][1]["trace_id"]
