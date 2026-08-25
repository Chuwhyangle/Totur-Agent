"""显式学习进度触发、上下文注入和 Agent 工具测试。"""

from app.schemas.chat import ToolCallTrace, ToolTrace, TutorReply
from app.services.agent.context import AgentContext
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.react_orchestrator import ReactOrchestrator, _RunState
from app.services.agent.response_parser import ResponseParser
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.agent.tools.update_learning_progress import SCHEMA
from app.services.agent.workspace.context import AgentExecutionContext
from app.services.learning_progress_service import LearningProgressService
from app.services.learning_progress_trigger import is_progress_update_request
from app.services.tutor_agent_service import TutorAgentService


def _execution_context(*, requested: bool) -> AgentExecutionContext:
    return AgentExecutionContext(
        user_id="alice",
        session_id=1,
        workspace_id=None,
        trace_id="trace-1",
        current_goal="/更新进度",
        task_recorder=None,
        progress_update_requested=requested,
    )


def test_progress_trigger_accepts_command_and_explicit_phrases_only():
    assert is_progress_update_request("/更新进度") is True
    assert is_progress_update_request("帮我去更新一下学习进度。") is True
    assert is_progress_update_request("更新我们的学习进度") is True
    assert is_progress_update_request("请根据最近的学习情况更新一下") is True
    assert is_progress_update_request("帮我分析并更新 SQL 学习进度") is True
    assert is_progress_update_request("请解释一下 JOIN") is False
    assert is_progress_update_request("学习进度是什么") is False
    assert is_progress_update_request("如何更新学习进度") is False


def test_progress_tool_is_hidden_unless_explicitly_requested():
    registry = ToolRegistry(mcp_client_adapter=object())

    ordinary_names = {
        item["function"]["name"] for item in registry.get_tools_schema()
    }
    update_names = {
        item["function"]["name"]
        for item in registry.get_tools_schema(_execution_context(requested=True))
    }
    active_names = {
        item["function"]["name"]
        for item in ReactOrchestrator(tool_registry=registry)._active_tools(
            execution_context=_execution_context(requested=True),
        )
    }

    assert "update_learning_progress" not in ordinary_names
    assert "update_learning_progress" in update_names
    assert active_names == {"update_learning_progress"}

    rejected = ToolExecutor(registry).execute(
        "update_learning_progress",
        {"updates": []},
        execution_context=_execution_context(requested=False),
    )
    assert rejected["error"] == "progress_update_not_requested"


def test_progress_tool_schema_explains_parameters_and_example():
    description = SCHEMA["function"]["description"]
    properties = SCHEMA["function"]["parameters"]["properties"]["updates"]["items"]["properties"]

    assert "save_journal_entry" in description
    assert "窗口函数" in description
    assert "知识点" in properties["topic"]["description"]
    assert "具体学习证据" in properties["evidence"]["description"]


def test_failed_progress_tool_call_is_retried_and_success_stops_retry():
    orchestrator = ReactOrchestrator(tool_registry=ToolRegistry(mcp_client_adapter=object()))
    run_state = _RunState(
        progress_update_requested=True,
        progress_update_round=1,
    )
    failed = ToolCallTrace(
        round=1,
        name="update_learning_progress",
        arguments={},
        ok=False,
    )
    succeeded = ToolCallTrace(
        round=2,
        name="update_learning_progress",
        arguments={},
        ok=True,
    )

    orchestrator._update_progress_retry_state(run_state, [failed])
    retry_choice = orchestrator._resolve_tool_choice(run_state, 2)
    assert retry_choice["function"]["name"] == "update_learning_progress"

    orchestrator._update_progress_retry_state(run_state, [succeeded])
    assert orchestrator._resolve_tool_choice(run_state, 3) == "none"


def test_progress_tool_updates_shared_records_and_preserves_higher_agent_level():
    service = LearningProgressService()
    service.save_manual(
        user_id="alice",
        subject="sql",
        topic="JOIN",
        level=3,
        status="mastered",
        evidence="已完成基础 JOIN 练习",
        next_step="练习复杂多表查询",
    )

    result = ToolExecutor(ToolRegistry(mcp_client_adapter=None)).execute(
        "update_learning_progress",
        {
            "updates": [
                {
                    "topic": "JOIN",
                    "level": 1,
                    "status": "needs_practice",
                    "evidence": "本次练习中连接条件写错",
                    "next_step": "复习 ON 和 WHERE 的区别",
                    "confidence": "high",
                }
            ]
        },
        execution_context=_execution_context(requested=True),
    )

    assert result["ok"] is True
    assert result["updated"][0]["previous_level"] == 3
    assert result["updated"][0]["current_level"] == 3
    assert result["updated"][0]["status"] == "needs_practice"


def test_progress_update_reply_is_guarded_when_tool_did_not_succeed():
    reply = TutorReply(answer="已经更新了学习进度", sources=[])
    failed_trace = ToolTrace(
        used=True,
        calls=[ToolCallTrace(round=1, name="update_learning_progress", arguments={}, ok=False)],
    )
    successful_trace = ToolTrace(
        used=True,
        calls=[ToolCallTrace(round=1, name="update_learning_progress", arguments={}, ok=True)],
    )

    guarded = TutorAgentService._guard_progress_update_reply(
        reply,
        progress_update_requested=True,
        tool_trace=failed_trace,
    )
    unchanged = TutorAgentService._guard_progress_update_reply(
        reply,
        progress_update_requested=True,
        tool_trace=successful_trace,
    )

    assert "长期学习记录未修改" in guarded.answer
    assert unchanged.answer == reply.answer


def test_prompt_builder_includes_progress_and_explicit_update_mode():
    context = AgentContext(
        user_id="alice",
        session_id=1,
        current_message="/更新进度",
        summary_text=None,
        recent_history=[],
        learning_progress=[
            LearningProgressService().save_manual(
                user_id="alice",
                subject="sql",
                topic="GROUP BY",
                level=2,
                status="learning",
                evidence="能完成基础分组题",
                next_step="练习 HAVING",
            )
        ],
        progress_update_requested=True,
    )

    messages = PromptBuilder(ResponseParser()).build_messages(context)
    contents = [str(message["content"]) for message in messages]

    progress_message = next(content for content in contents if "SQL_LEARNING_PROGRESS" in content)
    assert "GROUP BY" in progress_message
    assert "用户明确请求更新学习进度" in progress_message
    assert messages[-1]["content"] == "/更新进度"
