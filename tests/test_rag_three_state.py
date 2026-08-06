"""RAG 三态控制与可信 Note 来源单元测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.services.agent.react_orchestrator import ReactOrchestrator
from app.services.agent.tools.executor import ToolExecutor


FINAL_REPLY = """
{
  "answer": "已经完成分析。",
  "next_task": "整理下一步。",
  "exercise": "写一个小练习。",
  "checkpoints": ["能解释目标", "能说明依据", "能执行下一步"]
}
"""


class StubToolRegistry:
    """In-memory registry with configurable schema and tool map."""

    def __init__(
        self,
        tools: dict[str, Any] | None = None,
        schemas: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tools = tools or {}
        self._schemas = schemas or []

    def get_tools_schema(self) -> list[dict[str, Any]]:
        return list(self._schemas)

    def get_tool(self, name: str):
        return self._tools.get(name)

    def is_external_tool(self, name: str) -> bool:
        return False


RAG_SCHEMA = {"type": "function", "function": {"name": "search_learning_notes", "parameters": {}}}
WEB_SCHEMA = {"type": "function", "function": {"name": "web_search", "parameters": {}}}
JD_SCHEMA = {"type": "function", "function": {"name": "score_jd_skill_fit", "parameters": {}}}


def make_orchestrator(
    registry: StubToolRegistry | None = None,
    executor: ToolExecutor | None = None,
) -> ReactOrchestrator:
    registry = registry or StubToolRegistry()
    return ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(),
        tool_registry=registry,
        tool_executor=executor or ToolExecutor(registry),
    )


def final_message(content: str = FINAL_REPLY):
    return {"content": content, "tool_calls": []}


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def tool_call_message(*calls: dict[str, Any]):
    return {"content": None, "tool_calls": list(calls)}


def learning_notes_tool(query: str) -> dict[str, Any]:
    return {
        "ok": True,
        "found": True,
        "query": query,
        "count": 1,
        "items": [
            {
                "title": "FastAPI notes",
                "content": "FastAPI 依赖注入教程内容。",
                "source": "docs/backend/fastapi.md",
                "title_path": "FastAPI 依赖注入",
                "similarity": 0.91,
                "match_score": 91,
                "raw_text_excerpt": "FastAPI 依赖注入教程内容。",
            }
        ],
        "summary": {"returned_count": 1},
    }


def no_hit_tool(query: str) -> dict[str, Any]:
    return {
        "ok": True,
        "found": False,
        "query": query,
        "count": 0,
        "items": [],
        "message": "未找到相关笔记。",
        "summary": {"returned_count": 0},
    }


def embedding_failed_tool(query: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "embedding_failed",
        "message": "知识库检索失败，请稍后重试。",
    }


def index_not_built_tool(query: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "index_not_built",
        "message": "请先运行 scripts/build_knowledge_index.py 构建学习笔记索引。",
    }


class TestChatRequestThreeState:
    def test_old_requests_default_to_auto_mode(self):
        request = ChatRequest(user_id="alice", message="question")
        assert request.rag_enabled is True
        assert request.force_rag is False
        assert request.web_search_enabled is True
        assert request.force_web_search is False

    def test_force_mode_fields(self):
        request = ChatRequest(
            user_id="alice",
            message="question",
            rag_enabled=True,
            force_rag=True,
        )
        assert request.rag_enabled is True
        assert request.force_rag is True

    def test_off_mode_fields(self):
        request = ChatRequest(
            user_id="alice",
            message="question",
            rag_enabled=False,
            force_rag=False,
        )
        assert request.rag_enabled is False

    def test_rejects_force_rag_without_rag_enabled(self):
        with pytest.raises(ValidationError):
            ChatRequest(
                user_id="alice",
                message="question",
                rag_enabled=False,
                force_rag=True,
            )

    def test_web_search_off_mode_fields(self):
        request = ChatRequest(
            user_id="alice",
            message="question",
            web_search_enabled=False,
            force_web_search=False,
        )
        assert request.web_search_enabled is False

    def test_rejects_force_web_search_without_web_search_enabled(self):
        with pytest.raises(ValidationError):
            ChatRequest(
                user_id="alice",
                message="question",
                web_search_enabled=False,
                force_web_search=True,
            )


class TestRagDisabledMode:
    def test_rag_disabled_removes_tool_from_model_schema(self):
        registry = StubToolRegistry(
            tools={"web_search": lambda query: {"ok": True, "items": []}},
            schemas=[RAG_SCHEMA, WEB_SCHEMA, JD_SCHEMA],
        )
        captured_tools: dict[str, Any] = {}

        def fake_create(**kwargs):
            captured_tools["tools"] = kwargs.get("tools")
            return SimpleNamespace(
                choices=[SimpleNamespace(message={"content": "ok", "tool_calls": []})]
            )

        orchestrator = make_orchestrator(registry)
        orchestrator.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        orchestrator._active_rag_enabled = False

        orchestrator._call_model_with_tools([{"role": "user", "content": "hi"}])

        names = [
            tool["function"]["name"]
            for tool in captured_tools["tools"]
            if isinstance(tool, dict)
        ]
        assert "search_learning_notes" not in names
        assert "web_search" in names
        assert "score_jd_skill_fit" in names

    def test_rag_enabled_keeps_tool_in_model_schema(self):
        registry = StubToolRegistry(schemas=[RAG_SCHEMA, WEB_SCHEMA])
        captured_tools: dict[str, Any] = {}

        def fake_create(**kwargs):
            captured_tools["tools"] = kwargs.get("tools")
            return SimpleNamespace(
                choices=[SimpleNamespace(message={"content": "ok", "tool_calls": []})]
            )

        orchestrator = make_orchestrator(registry)
        orchestrator.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        orchestrator._active_rag_enabled = True

        orchestrator._call_model_with_tools([{"role": "user", "content": "hi"}])

        names = [
            tool["function"]["name"]
            for tool in captured_tools["tools"]
            if isinstance(tool, dict)
        ]
        assert "search_learning_notes" in names

    def test_rag_disabled_blocks_forged_model_rag_call(self):
        """关闭模式下，即使模型伪造 RAG 工具调用也不执行检索。"""

        executed_queries: list[str] = []

        def captured(query: str) -> dict[str, Any]:
            executed_queries.append(query)
            return learning_notes_tool(query)

        registry = StubToolRegistry({"search_learning_notes": captured})
        orchestrator = make_orchestrator(registry)
        model_call_count = 0
        messages_seen_by_final: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("search_learning_notes", {"query": "fake"}, "call_1")
                )
            messages_seen_by_final.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "q"}],
            rag_enabled=False,
            force_rag=False,
        )

        assert executed_queries == []
        assert tool_trace.calls[0].ok is False
        assert tool_trace.calls[0].error == "tool_disabled"
        tool_messages = [
            message
            for message in messages_seen_by_final
            if message["role"] == "tool"
        ]
        assert "tool_disabled" in tool_messages[0]["content"]


class TestWebSearchThreeState:
    def test_web_search_disabled_removes_tool_from_model_schema(self):
        registry = StubToolRegistry(
            tools={"web_search": lambda query: {"ok": True, "items": []}},
            schemas=[RAG_SCHEMA, WEB_SCHEMA, JD_SCHEMA],
        )
        captured_tools: dict[str, Any] = {}

        def fake_create(**kwargs):
            captured_tools["tools"] = kwargs.get("tools")
            return SimpleNamespace(
                choices=[SimpleNamespace(message={"content": "ok", "tool_calls": []})]
            )

        orchestrator = make_orchestrator(registry)
        orchestrator.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        orchestrator._active_rag_enabled = True
        orchestrator._active_web_search_enabled = False

        orchestrator._call_model_with_tools([{"role": "user", "content": "hi"}])

        names = [
            tool["function"]["name"]
            for tool in captured_tools["tools"]
            if isinstance(tool, dict)
        ]
        assert "web_search" not in names
        assert "search_learning_notes" in names
        assert "score_jd_skill_fit" in names

    def test_web_search_disabled_blocks_forged_model_call(self):
        """关闭模式下，即使模型伪造联网搜索调用也不执行。"""

        executed_queries: list[str] = []

        def captured(query: str) -> dict[str, Any]:
            executed_queries.append(query)
            return {"ok": True, "items": [], "summary": {"returned_count": 0}}

        registry = StubToolRegistry({"web_search": captured})
        orchestrator = make_orchestrator(registry)
        model_call_count = 0
        messages_seen_by_final: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("web_search", {"query": "fake"}, "call_1")
                )
            messages_seen_by_final.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "q"}],
            web_search_enabled=False,
            force_web_search=False,
        )

        assert executed_queries == []
        assert tool_trace.calls[0].ok is False
        assert tool_trace.calls[0].error == "tool_disabled"
        tool_messages = [
            message
            for message in messages_seen_by_final
            if message["role"] == "tool"
        ]
        assert "tool_disabled" in tool_messages[0]["content"]

    def test_web_search_enabled_auto_mode_still_executes(self):
        """自动模式（enabled=true, force=false）保持模型自主调用。"""

        executed_queries: list[str] = []

        def captured(query: str) -> dict[str, Any]:
            executed_queries.append(query)
            return {
                "ok": True,
                "found": True,
                "items": [
                    {
                        "title": "Web A",
                        "url": "https://example.com/a",
                        "snippet": "a",
                        "domain": "untrusted.example",
                    }
                ],
                "summary": {"returned_count": 1},
            }

        registry = StubToolRegistry({"web_search": captured})
        orchestrator = make_orchestrator(registry)
        model_call_count = 0

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("web_search", {"query": "latest"}, "call_1")
                )
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run([{"role": "user", "content": "q"}])

        assert executed_queries == ["latest"]
        assert tool_trace.calls[0].ok is True
        assert tool_trace.ledger["web_1"].domain == "example.com"


class TestForceRagMode:
    def test_force_rag_runs_before_first_model_call(self):
        executed_queries: list[str] = []

        def captured(query: str) -> dict[str, Any]:
            executed_queries.append(query)
            return learning_notes_tool(query)

        registry = StubToolRegistry({"search_learning_notes": captured})
        orchestrator = make_orchestrator(registry)
        messages_seen_by_model: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            messages_seen_by_model.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        raw_reply, tool_trace = orchestrator.run(
            [
                {"role": "user", "content": "Earlier question"},
                {"role": "user", "content": "FastAPI 依赖注入怎么用？"},
            ],
            rag_enabled=True,
            force_rag=True,
        )

        assert raw_reply == FINAL_REPLY
        assert executed_queries == ["FastAPI 依赖注入怎么用？"]
        assert tool_trace.used is True
        assert len(tool_trace.calls) == 1
        assert tool_trace.calls[0].name == "search_learning_notes"
        assert tool_trace.calls[0].round == 1
        assert tool_trace.calls[0].ok is True
        tool_messages = [
            message
            for message in messages_seen_by_model
            if message["role"] == "tool"
        ]
        assert len(tool_messages) == 1
        observation = json.loads(tool_messages[0]["content"])
        assert observation["items"][0]["evidence_id"] == "note_1"
        assert tool_trace.ledger["note_1"].domain == "knowledge_note"
        assert tool_trace.ledger["note_1"].url == ""
        assert "docs/backend/fastapi.md" in tool_trace.ledger["note_1"].title

    def test_force_rag_reuses_executor_default_subject(self):
        executed_kwargs: dict[str, Any] = {}

        def captured(**kwargs) -> dict[str, Any]:
            executed_kwargs.update(kwargs)
            return learning_notes_tool(kwargs.get("query") or "")

        registry = StubToolRegistry({"search_learning_notes": captured})
        executor = ToolExecutor(registry)
        executor.set_default_tool_kwargs(
            {"search_learning_notes": {"subject": "computer-science"}}
        )
        orchestrator = make_orchestrator(registry, executor)
        orchestrator._call_model_with_tools = lambda _messages: final_message()

        orchestrator.run(
            [{"role": "user", "content": "FastAPI notes"}],
            rag_enabled=True,
            force_rag=True,
        )

        assert executed_kwargs.get("query") == "FastAPI notes"
        assert executed_kwargs.get("subject") == "computer-science"

    def test_force_rag_does_not_consume_react_rounds(self):
        registry = StubToolRegistry(
            {"search_learning_notes": learning_notes_tool}
        )
        orchestrator = make_orchestrator(registry)
        orchestrator.max_steps = 2
        model_call_count = 0
        messages_seen: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            messages_seen.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "notes"}],
            rag_enabled=True,
            force_rag=True,
        )

        # 强制预检索不消耗 ReAct 轮数：模型第一轮调用就携带了检索
        # observation，且没有为检索消耗任何工具轮次。
        assert model_call_count == 1
        tool_messages = [
            message for message in messages_seen if message["role"] == "tool"
        ]
        assert len(tool_messages) == 1
        assert len(tool_trace.calls) == 1

    def test_force_rag_orders_before_forced_web_search(self):
        def web_search(query: str) -> dict[str, Any]:
            return {
                "ok": True,
                "found": True,
                "query": query,
                "items": [
                    {
                        "title": "Web source",
                        "url": "https://example.com/page",
                        "snippet": "evidence",
                        "domain": "untrusted.example",
                    }
                ],
                "summary": {"returned_count": 1, "provider": "stub"},
            }

        registry = StubToolRegistry(
            {
                "search_learning_notes": learning_notes_tool,
                "web_search": web_search,
            }
        )
        orchestrator = make_orchestrator(registry)
        messages_seen_by_model: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            messages_seen_by_model.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "latest FastAPI"}],
            force_web_search=True,
            rag_enabled=True,
            force_rag=True,
        )

        assert [call.name for call in tool_trace.calls] == [
            "search_learning_notes",
            "web_search",
        ]
        assert [call.round for call in tool_trace.calls] == [1, 2]
        tool_messages = [
            message
            for message in messages_seen_by_model
            if message["role"] == "tool"
        ]
        assert len(tool_messages) == 2
        assert "note_1" in json.loads(tool_messages[0]["content"])["items"][0]["evidence_id"]
        assert "web_1" in json.loads(tool_messages[1]["content"])["items"][0]["evidence_id"]
        assert set(tool_trace.ledger) == {"note_1", "web_1"}


class TestAutoModeNoteLedger:
    def test_auto_mode_assigns_note_ids_when_model_calls_rag(self):
        registry = StubToolRegistry(
            {"search_learning_notes": learning_notes_tool}
        )
        orchestrator = make_orchestrator(registry)
        model_call_count = 0
        messages_seen_by_final: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("search_learning_notes", {"query": "notes"}, "call_1")
                )
            messages_seen_by_final.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run([{"role": "user", "content": "q"}])

        tool_messages = [
            message
            for message in messages_seen_by_final
            if message["role"] == "tool"
        ]
        observation = json.loads(tool_messages[0]["content"])
        assert observation["items"][0]["evidence_id"] == "note_1"
        assert tool_trace.ledger["note_1"].domain == "knowledge_note"

    def test_same_note_fingerprint_reuses_note_id_across_calls(self):
        registry = StubToolRegistry(
            {"search_learning_notes": learning_notes_tool}
        )
        orchestrator = make_orchestrator(registry)
        model_call_count = 0
        messages_seen_by_final: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("search_learning_notes", {"query": "first"}, "call_1")
                )
            if model_call_count == 2:
                return tool_call_message(
                    tool_call("search_learning_notes", {"query": "second"}, "call_2")
                )
            messages_seen_by_final.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run([{"role": "user", "content": "q"}])

        assert set(tool_trace.ledger) == {"note_1"}
        observations = [
            json.loads(message["content"])["items"][0]["evidence_id"]
            for message in messages_seen_by_final
            if message["role"] == "tool"
        ]
        assert observations == ["note_1", "note_1"]

    def test_auto_mode_remains_functional_for_other_tools(self):
        registry = StubToolRegistry(
            {
                "search_learning_notes": learning_notes_tool,
                "web_search": lambda query: {
                    "ok": True,
                    "found": True,
                    "items": [
                        {
                            "title": "Web A",
                            "url": "https://example.com/a",
                            "snippet": "a",
                            "domain": "untrusted.example",
                        }
                    ],
                    "summary": {"returned_count": 1},
                },
            }
        )
        orchestrator = make_orchestrator(registry)
        model_call_count = 0

        def fake_call_model_with_tools(messages):
            nonlocal model_call_count
            model_call_count += 1
            if model_call_count == 1:
                return tool_call_message(
                    tool_call("search_learning_notes", {"query": "notes"}, "call_1")
                )
            if model_call_count == 2:
                return tool_call_message(
                    tool_call("web_search", {"query": "web"}, "call_2")
                )
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run([{"role": "user", "content": "q"}])

        assert set(tool_trace.ledger) == {"note_1", "web_1"}


class TestRagFailurePaths:
    def test_force_rag_no_hit_does_not_create_note_ids(self):
        registry = StubToolRegistry({"search_learning_notes": no_hit_tool})
        orchestrator = make_orchestrator(registry)
        messages_seen_by_model: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            messages_seen_by_model.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "unknown private topic"}],
            rag_enabled=True,
            force_rag=True,
        )

        assert tool_trace.ledger == {}
        tool_messages = [
            message
            for message in messages_seen_by_model
            if message["role"] == "tool"
        ]
        observation = json.loads(tool_messages[0]["content"])
        assert observation["ok"] is True
        assert observation["found"] is False
        assert observation["items"] == []

    def test_force_rag_index_not_built_uses_stable_message(self):
        registry = StubToolRegistry({"search_learning_notes": index_not_built_tool})
        orchestrator = make_orchestrator(registry)
        messages_seen_by_model: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            messages_seen_by_model.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "notes"}],
            rag_enabled=True,
            force_rag=True,
        )

        assert tool_trace.ledger == {}
        tool_messages = [
            message
            for message in messages_seen_by_model
            if message["role"] == "tool"
        ]
        observation = json.loads(tool_messages[0]["content"])
        assert observation["ok"] is False
        assert observation["error"] == "index_not_built"
        assert observation["message"] == "本地知识库索引尚未构建，当前无法执行 RAG 检索。"

    def test_force_rag_embedding_failure_does_not_leak_details(self):
        registry = StubToolRegistry(
            {"search_learning_notes": embedding_failed_tool}
        )
        orchestrator = make_orchestrator(registry)
        messages_seen_by_model: list[dict[str, Any]] = []

        def fake_call_model_with_tools(messages):
            messages_seen_by_model.extend(messages)
            return final_message()

        orchestrator._call_model_with_tools = fake_call_model_with_tools

        _, tool_trace = orchestrator.run(
            [{"role": "user", "content": "notes"}],
            rag_enabled=True,
            force_rag=True,
        )

        assert tool_trace.ledger == {}
        assert tool_trace.calls[0].ok is False
        tool_messages = [
            message
            for message in messages_seen_by_model
            if message["role"] == "tool"
        ]
        observation = json.loads(tool_messages[0]["content"])
        assert observation["error"] == "embedding_failed"
        assert observation["message"] == "本轮知识库检索失败，无法提供本地资料。"


class TestStreamingMode:
    def test_stream_force_rag_yields_tool_events_then_reply(self):
        registry = StubToolRegistry(
            {"search_learning_notes": learning_notes_tool}
        )
        orchestrator = make_orchestrator(registry)
        orchestrator._call_model_with_tools = lambda _messages: final_message()
        orchestrator._stream_final_reply = lambda _messages: iter(
            [
                SimpleNamespace(type="token", data={"text": "streamed "}),
                SimpleNamespace(type="token", data={"text": "reply"}),
            ]
        )

        stream = orchestrator.run_stream(
            [{"role": "user", "content": "notes"}],
            rag_enabled=True,
            force_rag=True,
        )
        events: list[tuple[str, str]] = []
        while True:
            try:
                event = next(stream)
                events.append((event.type, event.data.get("text", "")))
            except StopIteration as stop:
                raw_reply, tool_trace = stop.value
                break

        assert events[0][0] == "tool_call"
        assert events[1][0] == "tool_result"
        assert "".join(text for kind, text in events if kind == "token") == "streamed reply"
        assert raw_reply == "streamed reply"
        assert set(tool_trace.ledger) == {"note_1"}
