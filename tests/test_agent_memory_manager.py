"""Agent 记忆管理器的单元测试。"""

import json

from app.db import database
from app.repositories.conversation_repository import (
    list_recent_conversations,
    save_conversation,
)
from app.repositories.session_repository import create_session
from app.repositories.summary_repository import upsert_summary
from app.schemas.chat import TutorReply
from app.services.agent.context import AgentContext
from app.services.agent.memory_manager import MemoryManager
from app.services.memory_settings import RECENT_HISTORY_LIMIT


class FakeSummaryService:
    """用于记录摘要更新调用的测试替身。"""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.updated_session_ids: list[int] = []

    def update_summary_if_needed(self, session_id: int) -> bool:
        self.updated_session_ids.append(session_id)
        if self.should_fail:
            raise RuntimeError("summary update failed")
        return False


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def _reply_json(answer: str) -> str:
    return json.dumps(
        {
            "answer": answer,
            "next_task": "下一步任务",
            "exercise": "小练习",
            "checkpoints": ["检查点"],
        },
        ensure_ascii=False,
    )


def test_load_context_reads_summary_and_recent_history(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice", "记忆读取")
    upsert_summary(
        session_id=session.id,
        summary_text="较早历史摘要",
        last_conversation_id=0,
    )

    for index in range(1, RECENT_HISTORY_LIMIT + 2):
        save_conversation(
            user_id="alice",
            session_id=session.id,
            message=f"历史问题 {index}",
            reply_json=_reply_json(f"历史回答 {index}"),
        )

    manager = MemoryManager(FakeSummaryService())

    context = manager.load_context(
        user_id="alice",
        session_id=session.id,
        current_message="当前问题",
    )

    assert isinstance(context, AgentContext)
    assert context.user_id == "alice"
    assert context.session_id == session.id
    assert context.current_message == "当前问题"
    assert context.summary_text == "较早历史摘要"
    assert len(context.recent_history) == RECENT_HISTORY_LIMIT
    assert [record.message for record in context.recent_history] == [
        f"历史问题 {index}"
        for index in range(RECENT_HISTORY_LIMIT + 1, 1, -1)
    ]


def test_save_turn_and_update_summary_saves_conversation_and_triggers_summary(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice", "记忆保存")
    summary_service = FakeSummaryService()
    manager = MemoryManager(summary_service)
    reply = TutorReply(
        answer="本轮回答",
        next_task="下一步任务",
        exercise="小练习",
        checkpoints=["检查点"],
    )

    manager.save_turn_and_update_summary(
        user_id="alice",
        session_id=session.id,
        message="本轮问题",
        reply=reply,
    )

    records = list_recent_conversations(
        user_id="alice",
        session_id=session.id,
        limit=1,
    )
    saved_reply = json.loads(records[0].reply_json)

    assert records[0].message == "本轮问题"
    assert saved_reply["answer"] == "本轮回答"
    assert summary_service.updated_session_ids == [session.id]


def test_save_turn_and_update_summary_ignores_summary_failure(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice", "摘要失败")
    manager = MemoryManager(FakeSummaryService(should_fail=True))
    reply = TutorReply(
        answer="失败时仍然保存",
        next_task="下一步任务",
        exercise="小练习",
        checkpoints=["检查点"],
    )

    manager.save_turn_and_update_summary(
        user_id="alice",
        session_id=session.id,
        message="摘要失败也要保存",
        reply=reply,
    )

    records = list_recent_conversations(
        user_id="alice",
        session_id=session.id,
        limit=1,
    )
    assert records[0].message == "摘要失败也要保存"

