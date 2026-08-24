"""Focused integration coverage for Workspace-aware Agent execution."""

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.db.models import WorkspaceTaskStatus
from app.repositories import workspace_task_repository
from app.repositories import workspace_artifact_repository
from app.repositories.session_repository import create_session
from app.schemas.chat import ToolTrace
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.agent.workspace import AgentExecutionContext, WorkspaceTaskRecorder
from app.services.tutor_agent_service import TutorAgentService
from app.services.workspaces.asset_processing_service import AssetProcessingService
from app.services.workspaces.asset_service import AssetService
from app.services.workspaces.workspace_service import WorkspaceService


def make_workspace_context(*, user_id: str = "alice", goal: str = "整理 Workspace 资料"):
    workspace = WorkspaceService().create_workspace(user_id=user_id, name="Agent test")
    session = create_session(user_id=user_id, workspace_id=workspace.id)
    recorder = WorkspaceTaskRecorder(
        user_id=user_id,
        session_id=session.id,
        workspace_id=workspace.id,
        trace_id=str(uuid4()),
        current_goal=goal,
    )
    context = AgentExecutionContext(
        user_id=user_id,
        session_id=session.id,
        workspace_id=workspace.id,
        trace_id=recorder.trace_id,
        current_goal=goal,
        task_recorder=recorder,
    )
    return workspace, session, context


def make_ready_text_asset(workspace_id: str, user_id: str = "alice"):
    asset, _ = AssetService().upload(
        user_id=user_id,
        workspace_id=workspace_id,
        file_stream=BytesIO("FastAPI Agent Workspace\n第二行资料".encode()),
        original_filename="notes.txt",
        media_type="TEXT/PLAIN",
    )
    AssetProcessingService().process(asset.id)
    return asset.id


def test_workspace_tools_are_context_gated_and_schema_has_no_identity_fields(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    registry = ToolRegistry(mcp_client_adapter=None)

    ordinary_names = {item["function"]["name"] for item in registry.get_tools_schema()}
    assert not ordinary_names.intersection({
        "list_workspace_assets",
        "read_workspace_asset",
        "search_workspace_assets",
        "create_markdown_artifact",
    })

    _, _, context = make_workspace_context()
    workspace_names = {item["function"]["name"] for item in registry.get_tools_schema(context)}
    assert {
        "list_workspace_assets",
        "read_workspace_asset",
        "search_workspace_assets",
        "create_markdown_artifact",
    }.issubset(workspace_names)
    schema_text = str(registry.get_tools_schema(context))
    assert "user_id" not in schema_text
    assert "workspace_id" not in schema_text
    assert "session_id" not in schema_text

    result = ToolExecutor(registry).execute("list_workspace_assets", {})
    assert result["error"] == "workspace_context_required"


def test_workspace_tools_share_task_record_steps_and_asset_refs(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, _, context = make_workspace_context()
    asset_id = make_ready_text_asset(workspace.id)
    executor = ToolExecutor(ToolRegistry(mcp_client_adapter=None))

    listed = executor.execute(
        "list_workspace_assets",
        {"status": "READY", "limit": 20},
        execution_context=context,
        tool_call_id="call-list",
    )
    read = executor.execute(
        "read_workspace_asset",
        {"asset_id": asset_id, "segment_count": 10},
        execution_context=context,
        tool_call_id="call-read",
    )
    searched = executor.execute(
        "search_workspace_assets",
        {"query": "Agent", "asset_ids": [asset_id]},
        execution_context=context,
        tool_call_id="call-search",
    )

    assert listed["items"][0]["asset_id"] == asset_id
    assert read["segments"][0]["segment_id"] == "s000001"
    assert searched["items"][0]["asset_id"] == asset_id
    assert context.task_recorder.task_id is not None
    task = workspace_task_repository.get_task(context.task_recorder.task_id)
    assert task is not None
    assert task.status is WorkspaceTaskStatus.RUNNING
    assert len(workspace_task_repository.list_task_steps(task.id)) == 3
    refs = workspace_task_repository.list_task_asset_refs(task.id)
    assert [ref.asset_id for ref in refs] == [asset_id]

    duplicate = executor.execute(
        "read_workspace_asset",
        {"asset_id": asset_id, "segment_count": 1},
        execution_context=context,
        tool_call_id="call-read",
    )
    assert duplicate["ok"] is True
    assert len(workspace_task_repository.list_task_steps(task.id)) == 3


def test_workspace_tool_rejects_foreign_asset_and_failed_step_adds_warning(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    first_workspace, _, context = make_workspace_context()
    second_workspace = WorkspaceService().create_workspace(user_id="alice", name="Other")
    foreign_asset_id = make_ready_text_asset(second_workspace.id)

    result = ToolExecutor(ToolRegistry(mcp_client_adapter=None)).execute(
        "read_workspace_asset",
        {"asset_id": foreign_asset_id},
        execution_context=context,
        tool_call_id="call-foreign",
    )

    assert result["ok"] is False
    assert result["error"] == "asset_not_found"
    task = workspace_task_repository.get_task(context.task_recorder.task_id)
    assert task.workspace_id == first_workspace.id
    assert task.warning_count == 1
    assert workspace_task_repository.list_task_steps(task.id)[0].error_code == "asset_not_found"


def test_create_artifact_uses_context_task_and_records_version_chain(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, _, context = make_workspace_context()
    asset_id = make_ready_text_asset(workspace.id)
    executor = ToolExecutor(ToolRegistry(mcp_client_adapter=None))

    first = executor.execute(
        "create_markdown_artifact",
        {"title": "报告", "markdown_content": "# v1", "source_asset_ids": [asset_id]},
        execution_context=context,
        tool_call_id="call-artifact-1",
    )
    first_artifact_id = first["artifact_id"]
    second = executor.execute(
        "create_markdown_artifact",
        {
            "title": "报告",
            "markdown_content": "# v2",
            "source_asset_ids": [asset_id],
            "supersedes_artifact_id": first_artifact_id,
        },
        execution_context=context,
        tool_call_id="call-artifact-2",
    )

    assert first["version_number"] == 1
    assert second["version_number"] == 2
    assert [source.asset_id for source in workspace_artifact_repository.list_sources(first_artifact_id)] == [asset_id]
    context.task_recorder.complete_task()
    assert workspace_task_repository.get_task(context.task_recorder.task_id).status is WorkspaceTaskStatus.COMPLETED


class _MemoryStub:
    def load_context(self, **_kwargs):
        return SimpleNamespace(recent_history=[], seed_knowledge_context=None, private_jd_context=None)

    def save_turn_and_update_summary(self, **_kwargs):
        return None


class _PromptStub:
    def build_messages(self, *_args, **_kwargs):
        return [{"role": "user", "content": "test"}]


def test_tutor_service_completes_workspace_task_after_normal_reply(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, session, context = make_workspace_context()
    executor = ToolExecutor(ToolRegistry(mcp_client_adapter=None))

    class OrchestratorStub:
        def run(self, _messages, execution_context=None, **_kwargs):
            executor.execute(
                "list_workspace_assets",
                {},
                execution_context=execution_context,
                tool_call_id="service-call",
            )
            return "# 完成", ToolTrace(used=True, calls=[], ledger={})

    service = TutorAgentService(
        memory_manager=_MemoryStub(),
        prompt_builder=_PromptStub(),
        react_orchestrator=OrchestratorStub(),
        seed_context_enabled=False,
    )
    response = service.chat(
        SimpleNamespace(
            user_id="alice",
            session_id=session.id,
            persona_id=session.persona_id,
            message="整理 Workspace 资料",
            model_id="ds-flash-fast",
            web_search_enabled=False,
            force_web_search=False,
            rag_enabled=False,
            force_rag=False,
            attachment_ids=[],
        )
    )

    assert response.reply.answer == "# 完成"
    tasks = workspace_task_repository.list_workspace_tasks(workspace.id)
    assert len(tasks) == 1
    assert tasks[0].status is WorkspaceTaskStatus.COMPLETED


def test_tutor_service_completes_with_warning_after_failed_workspace_tool(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, session, context = make_workspace_context()
    other_workspace = WorkspaceService().create_workspace(user_id="alice", name="Other")
    foreign_asset_id = make_ready_text_asset(other_workspace.id)
    executor = ToolExecutor(ToolRegistry(mcp_client_adapter=None))

    class OrchestratorStub:
        def run(self, _messages, execution_context=None, **_kwargs):
            executor.execute(
                "read_workspace_asset",
                {"asset_id": foreign_asset_id},
                execution_context=execution_context,
                tool_call_id="failed-service-call",
            )
            return "# 即使工具失败也回复", ToolTrace(used=True, calls=[], ledger={})

    service = TutorAgentService(
        memory_manager=_MemoryStub(),
        prompt_builder=_PromptStub(),
        react_orchestrator=OrchestratorStub(),
        seed_context_enabled=False,
    )
    service.chat(
        SimpleNamespace(
            user_id="alice", session_id=session.id, persona_id=session.persona_id,
            message="继续完成", model_id="ds-flash-fast", web_search_enabled=False,
            force_web_search=False, rag_enabled=False, force_rag=False, attachment_ids=[],
        )
    )

    task = workspace_task_repository.list_workspace_tasks(workspace.id)[0]
    assert task.status is WorkspaceTaskStatus.COMPLETED
    assert task.warning_count == 1


def test_stream_cancellation_fails_an_already_created_workspace_task(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, session, _ = make_workspace_context()

    class StreamOrchestratorStub:
        def run_stream(self, _messages, execution_context=None, **_kwargs):
            execution_context.task_recorder.ensure_task()
            yield SimpleNamespace(type="token", data={"text": "partial"})
            yield SimpleNamespace(type="token", data={"text": "never committed"})

    service = TutorAgentService(
        memory_manager=_MemoryStub(),
        prompt_builder=_PromptStub(),
        react_orchestrator=StreamOrchestratorStub(),
        seed_context_enabled=False,
    )
    request = SimpleNamespace(
        user_id="alice", session_id=session.id, persona_id=session.persona_id,
        message="流式取消", model_id="ds-flash-fast", web_search_enabled=False,
        force_web_search=False, rag_enabled=False, force_rag=False, attachment_ids=[],
    )
    stream = service.chat_stream(request)
    next(stream)
    stream.close()

    task = workspace_task_repository.list_workspace_tasks(workspace.id)[0]
    assert task.status is WorkspaceTaskStatus.FAILED
    assert task.error_code == "PROCESS_INTERRUPTED"


def test_archived_workspace_tool_is_rejected(monkeypatch):
    monkeypatch.setenv("ENABLE_WORKSPACES", "true")
    workspace, _, context = make_workspace_context()
    WorkspaceService().archive_workspace(user_id="alice", workspace_id=workspace.id)

    registry = ToolRegistry(mcp_client_adapter=None)
    assert not any(
        item["function"]["name"] == "list_workspace_assets"
        for item in registry.get_tools_schema(context)
    )
    result = ToolExecutor(registry).execute(
        "list_workspace_assets", {}, execution_context=context, tool_call_id="archived"
    )
    assert result["error"] == "workspace_archived"
