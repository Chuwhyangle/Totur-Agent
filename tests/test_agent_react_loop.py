"""Behavior tests for the Tutor Agent ReAct loop."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.services.agent.react_orchestrator import ReactOrchestrator


FINAL_REPLY = """
{
  "answer": "已经完成分析。",
  "next_task": "整理下一步。",
  "exercise": "写一个小练习。",
  "checkpoints": ["能解释目标", "能说明依据", "能执行下一步"]
}
"""


class StubToolRegistry:
    """Small in-memory registry so the ReAct tests do not touch app tools."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        """保存测试用工具映射，未传入时表示没有可用工具。"""

        self._tools = tools or {}

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """返回空 schema，让测试只关心 loop 行为。"""

        return []

    def get_tool(self, name: str):
        """按名称返回测试工具，找不到时返回 None。"""

        return self._tools.get(name)


def make_orchestrator(
    registry: StubToolRegistry | None = None,
) -> ReactOrchestrator:
    """创建不连接真实 LLM 的 ReactOrchestrator。"""

    return ReactOrchestrator(
        config=SimpleNamespace(model="test-model"),
        client=SimpleNamespace(),
        tool_registry=registry or StubToolRegistry(),
    )


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1"):
    """构造一个 OpenAI-compatible 的测试 tool_call。"""

    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def final_message(content: str = FINAL_REPLY):
    """构造一个不再请求工具的最终模型消息。"""

    return {
        "content": content,
        "tool_calls": [],
    }


def tool_call_message(*calls: dict[str, Any]):
    """构造一个请求执行工具的模型消息。"""

    return {
        "content": None,
        "tool_calls": list(calls),
    }


def lookup_tool(query: str) -> dict[str, Any]:
    """模拟查询类工具，返回一条可预览的结果。"""

    return {
        "ok": True,
        "summary": {"returned_count": 1},
        "items": [
            {
                "title": f"Result for {query}",
                "match_score": 91,
                "matched_fields": ["title"],
            }
        ],
    }


def score_tool(topic: str) -> dict[str, Any]:
    """模拟评分类工具，返回一条可预览的结果。"""

    return {
        "ok": True,
        "summary": {"returned_count": 1},
        "items": [{"title": f"Score for {topic}", "match_score": 80}],
    }


def test_react_loop_returns_model_content_when_no_tool_is_requested():
    """模型没有请求工具时，ReAct loop 应直接返回最终内容。"""

    orchestrator = make_orchestrator()

    def fake_call_model_with_tools(messages):
        """模拟模型直接给出最终答案。"""

        return final_message()

    orchestrator._call_model_with_tools = fake_call_model_with_tools

    raw_reply, tool_trace = orchestrator.run(
        [{"role": "user", "content": "解释 FastAPI。"}]
    )

    assert raw_reply == FINAL_REPLY
    assert tool_trace.used is False
    assert tool_trace.calls == []


def test_react_loop_continues_to_final_answer_after_one_tool_call():
    """执行一次工具后，应把 observation 回填给模型并拿到最终答案。"""

    registry = StubToolRegistry({"lookup": lookup_tool})
    orchestrator = make_orchestrator(registry)
    messages_seen_by_final_call = []
    model_call_count = 0

    def fake_call_model_with_tools(messages):
        """第一次请求工具，第二次观察工具结果后返回最终答案。"""

        nonlocal model_call_count
        model_call_count += 1
        if model_call_count == 1:
            return tool_call_message(tool_call("lookup", {"query": "agent"}))

        messages_seen_by_final_call.extend(messages)
        return final_message()

    orchestrator._call_model_with_tools = fake_call_model_with_tools

    raw_reply, tool_trace = orchestrator.run(
        [{"role": "user", "content": "查一下 agent。"}]
    )

    tool_messages = [
        message for message in messages_seen_by_final_call if message["role"] == "tool"
    ]
    assert raw_reply == FINAL_REPLY
    assert model_call_count == 2
    assert tool_trace.used is True
    assert len(tool_trace.calls) == 1
    assert tool_trace.calls[0].name == "lookup"
    assert tool_trace.calls[0].arguments == {"query": "agent"}
    assert tool_trace.calls[0].ok is True
    assert tool_trace.calls[0].returned_count == 1
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert json.loads(tool_messages[0]["content"])["ok"] is True


def test_react_loop_can_execute_a_second_tool_after_observing_the_first_result():
    """第一次工具 observation 之后，模型仍可继续请求第二个工具。"""

    registry = StubToolRegistry({"lookup": lookup_tool, "score": score_tool})
    orchestrator = make_orchestrator(registry)
    model_calls = []

    def fake_call_model_with_tools(messages):
        """前两次分别请求 lookup 和 score，第三次结束。"""

        model_calls.append(messages)
        if len(model_calls) == 1:
            return tool_call_message(tool_call("lookup", {"query": "agent"}))
        if len(model_calls) == 2:
            return tool_call_message(tool_call("score", {"topic": "agent"}, "call_2"))
        return final_message()

    def fake_call_model(messages):
        """兼容旧替换路径；本测试的 ReAct loop 不应调用它。"""

        return FINAL_REPLY

    orchestrator._call_model_with_tools = fake_call_model_with_tools
    orchestrator._call_model = fake_call_model

    raw_reply, tool_trace = orchestrator.run(
        [{"role": "user", "content": "先查资料再评分。"}]
    )

    assert raw_reply == FINAL_REPLY
    assert len(model_calls) == 3
    assert tool_trace.used is True
    assert [call.name for call in tool_trace.calls] == ["lookup", "score"]
    assert tool_trace.calls[1].arguments == {"topic": "agent"}
    assert tool_trace.calls[1].ok is True


def test_react_loop_stops_before_followup_model_call_when_max_steps_is_reached():
    """达到 max_react_steps 后，应停止继续请求模型并返回 fallback。"""

    registry = StubToolRegistry({"lookup": lookup_tool})
    orchestrator = make_orchestrator(registry)
    orchestrator.max_steps = 1
    final_model_call_count = 0

    def fake_call_model_with_tools(messages):
        """每次都请求工具，用来触发最大步数保护。"""

        return tool_call_message(tool_call("lookup", {"query": "agent"}))

    def fake_call_model(messages):
        """记录是否误入旧的一轮工具后 final 调用路径。"""

        nonlocal final_model_call_count
        final_model_call_count += 1
        return FINAL_REPLY

    orchestrator._call_model_with_tools = fake_call_model_with_tools
    orchestrator._call_model = fake_call_model

    raw_reply, tool_trace = orchestrator.run(
        [{"role": "user", "content": "一直查资料。"}]
    )

    assert final_model_call_count == 0
    assert tool_trace.used is True
    assert len(tool_trace.calls) == 1
    assert "最大步骤" in raw_reply


def test_react_loop_records_tool_errors_in_trace():
    """工具不存在时，错误应进入 trace，模型仍可基于 observation 收尾。"""

    orchestrator = make_orchestrator(StubToolRegistry())
    model_call_count = 0

    def fake_call_model_with_tools(messages):
        """第一次请求缺失工具，第二次看到错误 observation 后结束。"""

        nonlocal model_call_count
        model_call_count += 1
        if model_call_count == 1:
            return tool_call_message(tool_call("missing_tool", {"query": "agent"}))

        return final_message()

    orchestrator._call_model_with_tools = fake_call_model_with_tools

    raw_reply, tool_trace = orchestrator.run(
        [{"role": "user", "content": "调用缺失工具。"}]
    )

    assert raw_reply == FINAL_REPLY
    assert model_call_count == 2
    assert tool_trace.used is True
    assert len(tool_trace.calls) == 1
    assert tool_trace.calls[0].name == "missing_tool"
    assert tool_trace.calls[0].ok is False
    assert tool_trace.calls[0].error == "tool_not_found"


def test_react_loop_trace_keeps_a_stable_public_shape():
    """tool_trace 的公开字段结构应保持稳定，方便前端调试区消费。"""

    registry = StubToolRegistry({"lookup": lookup_tool})
    orchestrator = make_orchestrator(registry)
    model_call_count = 0

    def fake_call_model_with_tools(messages):
        """第一次请求工具，第二次结束，用来检查 trace 结构。"""

        nonlocal model_call_count
        model_call_count += 1
        if model_call_count == 1:
            return tool_call_message(tool_call("lookup", {"query": "agent"}))

        return final_message()

    orchestrator._call_model_with_tools = fake_call_model_with_tools

    _, tool_trace = orchestrator.run(
        [{"role": "user", "content": "查一下 agent。"}]
    )

    dumped = tool_trace.model_dump()

    assert len(dumped["calls"]) == 1
    assert set(dumped) == {"used", "calls"}
    assert set(dumped["calls"][0]) == {
        "name",
        "arguments",
        "ok",
        "returned_count",
        "top_titles",
        "result_preview",
        "error",
    }
    assert dumped["calls"][0]["result_preview"] == [
        {
            "title": "Result for agent",
            "match_score": 91,
            "matched_fields": ["title"],
            "core_skills": [],
            "keywords": [],
            "interview_focus": [],
            "raw_text_excerpt": "",
        }
    ]
