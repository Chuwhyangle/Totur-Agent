"""会话回档、恢复和永久删除测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.conversation_repository import list_recent_conversations, save_conversation
from app.repositories.session_repository import (
    archive_session,
    create_session,
    get_session,
    list_sessions,
)
from app.repositories.summary_repository import get_summary, upsert_summary


client = TestClient(app)


def test_archive_hides_session_but_restore_makes_it_visible():
    session = create_session("alice", "待整理的会话")

    archived_response = client.post(
        f"/sessions/{session.id}/archive?user_id=alice"
    )

    assert archived_response.status_code == 200
    assert archived_response.json()["archived_at"] is not None
    assert list_sessions("alice") == []
    assert [item.id for item in list_sessions("alice", include_archived=True)] == [session.id]

    foreign_response = client.post(
        f"/sessions/{session.id}/restore?user_id=bob"
    )
    assert foreign_response.status_code == 404

    restored_response = client.post(
        f"/sessions/{session.id}/restore?user_id=alice"
    )

    assert restored_response.status_code == 200
    assert restored_response.json()["archived_at"] is None
    assert list_sessions("alice")[0].id == session.id


def test_archive_is_idempotent_and_does_not_change_original_archive_time():
    session = create_session("alice", "可回档会话")

    first = archive_session(session.id, "alice")
    second = archive_session(session.id, "alice")

    assert first is not None
    assert second is not None
    assert first.archived_at == second.archived_at


def test_delete_permanently_removes_session_messages_and_summary():
    session = create_session("alice", "需要删除的会话")
    conversation_id = save_conversation(
        "alice",
        "需要删除的问题",
        '{"answer":"需要删除的回答"}',
        session_id=session.id,
    )
    upsert_summary(session.id, "需要删除的摘要", conversation_id)

    foreign_response = client.delete(f"/sessions/{session.id}?user_id=bob")
    assert foreign_response.status_code == 404
    assert get_session(session.id) is not None

    response = client.delete(f"/sessions/{session.id}?user_id=alice")

    assert response.status_code == 204
    assert get_session(session.id) is None
    assert list_sessions("alice", include_archived=True) == []
    assert list_recent_conversations("alice", session_id=session.id) == []
    assert get_summary(session.id) is None

    missing_response = client.delete(f"/sessions/{session.id}?user_id=alice")
    assert missing_response.status_code == 404
