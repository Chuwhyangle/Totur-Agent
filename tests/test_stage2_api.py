"""API acceptance tests for the current learning stages.

These tests avoid calling the real model. The chat route is tested with a
patched model response so the API structure is stable and repeatable.
"""

import sqlite3

from fastapi.testclient import TestClient

from app.db import database
from app.db.models import (
    CHAT_SESSIONS_TABLE,
    CONVERSATIONS_TABLE,
    DEFAULT_SESSION_TITLE,
)
from app.api.routes import chat as chat_route
from app.main import app
from app.repositories.conversation_repository import (
    list_recent_conversations,
    save_conversation,
)
from app.repositories.session_repository import (
    create_session,
    list_sessions,
    make_title_from_message,
)
from app.repositories.summary_repository import (
    count_unsummarized_conversations,
    get_summary,
    list_conversations_after,
    upsert_summary,
)
from app.services.tutor_agent_service import RECENT_HISTORY_LIMIT


client = TestClient(app)


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def test_initialize_database_migrates_old_conversations_into_default_sessions(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    connection = sqlite3.connect(database.DATABASE_PATH)
    try:
        connection.execute(
            f"""
            CREATE TABLE {CONVERSATIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                reply_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            f"""
            INSERT INTO {CONVERSATIONS_TABLE}
                (user_id, message, reply_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("alice", "first", "{}", "2026-01-01T00:00:00+00:00"),
                ("alice", "second", "{}", "2026-01-02T00:00:00+00:00"),
                ("bob", "bob question", "{}", "2026-01-03T00:00:00+00:00"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    database.initialize_database()

    connection = sqlite3.connect(database.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({CONVERSATIONS_TABLE})")
        }
        sessions = connection.execute(
            f"""
            SELECT id, user_id, title
            FROM {CHAT_SESSIONS_TABLE}
            ORDER BY user_id
            """
        ).fetchall()
        conversations = connection.execute(
            f"""
            SELECT user_id, session_id
            FROM {CONVERSATIONS_TABLE}
            ORDER BY id
            """
        ).fetchall()
    finally:
        connection.close()

    alice_session_ids = {
        row["session_id"] for row in conversations if row["user_id"] == "alice"
    }
    bob_session_ids = {
        row["session_id"] for row in conversations if row["user_id"] == "bob"
    }

    assert "session_id" in columns
    assert [(row["user_id"], row["title"]) for row in sessions] == [
        ("alice", DEFAULT_SESSION_TITLE),
        ("bob", DEFAULT_SESSION_TITLE),
    ]
    assert len(alice_session_ids) == 1
    assert len(bob_session_ids) == 1
    assert None not in alice_session_ids
    assert None not in bob_session_ids
    assert alice_session_ids != bob_session_ids


def test_save_conversation_assigns_default_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Default session answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """

    new_id = save_conversation("carol", "Create a default session.", reply_json)
    sessions = list_sessions("carol")
    records = list_recent_conversations("carol")

    assert len(sessions) == 1
    assert sessions[0].title == DEFAULT_SESSION_TITLE
    assert records[0].id == new_id
    assert records[0].session_id == sessions[0].id


def test_list_recent_conversations_can_filter_by_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Session answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """
    fastapi_session = create_session("alice", "FastAPI")
    sqlite_session = create_session("alice", "SQLite")

    save_conversation(
        "alice",
        "FastAPI question",
        reply_json,
        session_id=fastapi_session.id,
    )
    save_conversation(
        "alice",
        "SQLite question",
        reply_json,
        session_id=sqlite_session.id,
    )

    fastapi_history = list_recent_conversations(
        user_id="alice",
        session_id=fastapi_session.id,
    )
    sqlite_history = list_recent_conversations(
        user_id="alice",
        session_id=sqlite_session.id,
    )

    assert [record.message for record in fastapi_history] == ["FastAPI question"]
    assert [record.message for record in sqlite_history] == ["SQLite question"]


def test_get_summary_returns_none_when_session_has_no_summary(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    session = create_session("alice", "Summary base")

    assert get_summary(session.id) is None


def test_upsert_summary_creates_and_updates_one_summary(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Summary answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """
    session = create_session("alice", "Summary update")
    first_id = save_conversation(
        "alice",
        "first message",
        reply_json,
        session_id=session.id,
    )

    summary_id = upsert_summary(
        session_id=session.id,
        summary_text="Already summarized the first message.",
        last_conversation_id=first_id,
    )
    created_summary = get_summary(session.id)
    assert created_summary is not None
    assert created_summary.id == summary_id
    assert created_summary.session_id == session.id
    assert created_summary.summary_text == "Already summarized the first message."
    assert created_summary.last_conversation_id == first_id

    second_id = save_conversation(
        "alice",
        "second message",
        reply_json,
        session_id=session.id,
    )
    updated_id = upsert_summary(
        session_id=session.id,
        summary_text="Now summarized the first two messages.",
        last_conversation_id=second_id,
    )
    updated_summary = get_summary(session.id)

    assert updated_summary is not None
    assert updated_id == summary_id
    assert updated_summary.id == summary_id
    assert updated_summary.summary_text == "Now summarized the first two messages."
    assert updated_summary.last_conversation_id == second_id
    assert updated_summary.created_at <= updated_summary.updated_at


def test_summary_repository_counts_and_lists_unsummarized_messages(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "History answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """
    target_session = create_session("alice", "Target summary")
    other_session = create_session("alice", "Other summary")
    first_id = save_conversation(
        "alice",
        "target first",
        reply_json,
        session_id=target_session.id,
    )
    save_conversation(
        "alice",
        "other session message",
        reply_json,
        session_id=other_session.id,
    )
    save_conversation(
        "alice",
        "target second",
        reply_json,
        session_id=target_session.id,
    )
    save_conversation(
        "alice",
        "target third",
        reply_json,
        session_id=target_session.id,
    )

    upsert_summary(
        session_id=target_session.id,
        summary_text="Already summarized target first.",
        last_conversation_id=first_id,
    )

    assert count_unsummarized_conversations(target_session.id, first_id) == 2
    assert count_unsummarized_conversations(other_session.id, first_id) == 1

    records = list_conversations_after(
        session_id=target_session.id,
        after_id=first_id,
        limit=10,
    )
    limited_records = list_conversations_after(
        session_id=target_session.id,
        after_id=first_id,
        limit=1,
    )

    assert [record.message for record in records] == [
        "target second",
        "target third",
    ]
    assert [record.message for record in limited_records] == ["target second"]


def test_make_title_from_message_uses_first_message_and_truncates():
    assert make_title_from_message("  什么是 RAG？  ") == "什么是 RAG？"
    assert make_title_from_message("x" * 40) == f"{'x' * 30}..."


def test_post_sessions_creates_chat_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    response = client.post(
        "/sessions",
        json={
            "user_id": "alice",
            "title": "FastAPI 学习",
        },
    )

    assert response.status_code == 201
    body = response.json()

    assert body["id"] > 0
    assert body["user_id"] == "alice"
    assert body["title"] == "FastAPI 学习"
    assert isinstance(body["created_at"], str)
    assert isinstance(body["updated_at"], str)


def test_get_sessions_returns_only_current_user_sessions(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    first = create_session("alice", "FastAPI")
    second = create_session("alice", "SQLite")
    create_session("bob", "Bob session")

    response = client.get("/sessions?user_id=alice")

    assert response.status_code == 200
    body = response.json()

    assert body["user_id"] == "alice"
    assert [item["id"] for item in body["items"]] == [second.id, first.id]
    assert [item["title"] for item in body["items"]] == ["SQLite", "FastAPI"]
    assert all(item["user_id"] == "alice" for item in body["items"])


def test_get_sessions_respects_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    create_session("alice", "first")
    second = create_session("alice", "second")

    response = client.get("/sessions?user_id=alice&limit=1")

    assert response.status_code == 200
    body = response.json()

    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == second.id


def test_get_session_conversations_returns_messages_for_one_session(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Session answer",
      "next_task": "Session task",
      "exercise": "Session exercise",
      "checkpoints": ["Session checkpoint"]
    }
    """
    fastapi_session = create_session("alice", "FastAPI")
    sqlite_session = create_session("alice", "SQLite")
    save_conversation(
        "alice",
        "FastAPI question",
        reply_json,
        session_id=fastapi_session.id,
    )
    sqlite_id = save_conversation(
        "alice",
        "SQLite question",
        reply_json,
        session_id=sqlite_session.id,
    )

    response = client.get(f"/sessions/{sqlite_session.id}/conversations")

    assert response.status_code == 200
    body = response.json()

    assert body["session_id"] == sqlite_session.id
    assert body["user_id"] == "alice"
    assert body["title"] == "SQLite"
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == sqlite_id
    assert body["items"][0]["message"] == "SQLite question"
    assert body["items"][0]["reply"]["answer"] == "Session answer"


def test_get_session_conversations_respects_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """
    session = create_session("alice", "Limit test")
    save_conversation("alice", "first", reply_json, session_id=session.id)
    second_id = save_conversation("alice", "second", reply_json, session_id=session.id)

    response = client.get(f"/sessions/{session.id}/conversations?limit=1")

    assert response.status_code == 200
    body = response.json()

    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == second_id


def test_get_session_conversations_returns_404_for_missing_session():
    response = client.get("/sessions/999999/conversations")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_sessions_reject_invalid_limit():
    sessions_response = client.get("/sessions?user_id=alice&limit=0")
    conversations_response = client.get("/sessions/1/conversations?limit=0")

    assert sessions_response.status_code == 422
    assert conversations_response.status_code == 422


def test_health_returns_service_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "tutor-agent-api",
    }


def test_chat_returns_structured_reply(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "FastAPI routes connect a URL path and HTTP method to Python code.",
      "next_task": "Create one small GET route.",
      "exercise": "Write a /hello route that returns a short JSON message.",
      "checkpoints": [
        "The response has an answer",
        "The response has a next task",
        "The checkpoints are a list"
      ]
    }
    """

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: raw_model_reply,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "What is a FastAPI route?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    reply = body["reply"]

    assert body["user_id"] == "default"
    assert isinstance(body["session_id"], int)
    assert body["message"] == "What is a FastAPI route?"
    assert isinstance(reply["answer"], str)
    assert isinstance(reply["next_task"], str)
    assert isinstance(reply["exercise"], str)
    assert isinstance(reply["checkpoints"], list)
    assert len(reply["checkpoints"]) == 3


def test_chat_without_history_sends_only_current_user_message(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "No history answer",
      "next_task": "No history task",
      "exercise": "No history exercise",
      "checkpoints": ["No history checkpoint"]
    }
    """
    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，确认没有历史时只带当前用户问题。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "new-user",
            "message": "This user has no history.",
        },
    )

    assert response.status_code == 200

    role_and_content = [
        (message["role"], message["content"])
        for message in captured_messages
    ]
    assert role_and_content[1:] == [
        ("user", "This user has no history."),
    ]


def test_chat_saves_current_conversation_for_history_lookup(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "Saved answer",
      "next_task": "Saved task",
      "exercise": "Saved exercise",
      "checkpoints": ["Saved checkpoint"]
    }
    """

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: raw_model_reply,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Please save this turn.",
        },
    )

    assert response.status_code == 200

    history_response = client.get("/conversations/default")
    history_body = history_response.json()

    assert history_response.status_code == 200
    assert history_body["user_id"] == "default"
    assert history_body["items"][0]["message"] == "Please save this turn."
    assert history_body["items"][0]["reply"]["answer"] == "Saved answer"


def test_chat_uses_requested_session_for_history_and_saving(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    fastapi_session = create_session("alice", "FastAPI")
    sqlite_session = create_session("alice", "SQLite")
    fastapi_reply = """
    {
      "answer": "FastAPI previous answer",
      "next_task": "FastAPI task",
      "exercise": "FastAPI exercise",
      "checkpoints": ["FastAPI checkpoint"]
    }
    """
    sqlite_reply = """
    {
      "answer": "SQLite previous answer",
      "next_task": "SQLite task",
      "exercise": "SQLite exercise",
      "checkpoints": ["SQLite checkpoint"]
    }
    """
    raw_model_reply = """
    {
      "answer": "SQLite current answer",
      "next_task": "Current task",
      "exercise": "Current exercise",
      "checkpoints": ["Current checkpoint"]
    }
    """
    save_conversation(
        "alice",
        "FastAPI previous question",
        fastapi_reply,
        session_id=fastapi_session.id,
    )
    save_conversation(
        "alice",
        "SQLite previous question",
        sqlite_reply,
        session_id=sqlite_session.id,
    )
    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，确认只带当前 session_id 的历史。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": sqlite_session.id,
            "message": "Continue SQLite.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    sqlite_history = list_recent_conversations(
        user_id="alice",
        session_id=sqlite_session.id,
    )

    prompt_text = "\n".join(str(message["content"]) for message in captured_messages)
    assert body["session_id"] == sqlite_session.id
    assert "SQLite previous question" in prompt_text
    assert "SQLite previous answer" in prompt_text
    assert "FastAPI previous question" not in prompt_text
    assert "FastAPI previous answer" not in prompt_text
    assert sqlite_history[0].message == "Continue SQLite."


def test_chat_renames_empty_default_session_from_first_message(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    session = create_session("alice")
    raw_model_reply = """
    {
      "answer": "Title answer",
      "next_task": "Title task",
      "exercise": "Title exercise",
      "checkpoints": ["Title checkpoint"]
    }
    """

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: raw_model_reply,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": session.id,
            "message": "什么是 RAG？",
        },
    )

    assert response.status_code == 200
    sessions = list_sessions("alice")

    assert sessions[0].id == session.id
    assert sessions[0].title == "什么是 RAG？"


def test_chat_returns_404_for_missing_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": 999999,
            "message": "Use a missing session.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_chat_returns_404_for_other_users_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    bob_session = create_session("bob", "Bob session")

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "session_id": bob_session.id,
            "message": "Try to use Bob session.",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_chat_rejects_empty_message():
    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "",
        },
    )

    assert response.status_code == 422


def test_chat_rejects_empty_user_id():
    response = client.post(
        "/chat",
        json={
            "user_id": "",
            "message": "What is FastAPI?",
        },
    )

    assert response.status_code == 422


def test_chat_falls_back_when_model_reply_is_not_json(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        lambda messages: "This is not JSON, but the API should still respond.",
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Explain JSON parsing.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    reply = body["reply"]

    assert reply["answer"] == "This is not JSON, but the API should still respond."
    assert isinstance(reply["next_task"], str)
    assert isinstance(reply["exercise"], str)
    assert isinstance(reply["checkpoints"], list)
    assert len(reply["checkpoints"]) == 3


def test_chat_adds_history_user_and_assistant_messages(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    prior_reply = """
    {
      "answer": "Previous answer",
      "next_task": "Previous task",
      "exercise": "Previous exercise",
      "checkpoints": ["Previous checkpoint"]
    }
    """
    raw_model_reply = """
    {
      "answer": "Current answer",
      "next_task": "Current task",
      "exercise": "Current exercise",
      "checkpoints": ["Current checkpoint"]
    }
    """
    save_conversation("default", "Previous question", prior_reply)
    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，方便测试检查短期记忆上下文。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Continue from before.",
        },
    )

    assert response.status_code == 200

    role_and_content = [
        (message["role"], message["content"])
        for message in captured_messages
    ]
    assert role_and_content[1:] == [
        ("user", "Previous question"),
        ("assistant", "Previous answer"),
        ("user", "Continue from before."),
    ]


def test_chat_history_prompt_ignores_other_users(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    alice_reply = """
    {
      "answer": "Alice answer",
      "next_task": "Alice task",
      "exercise": "Alice exercise",
      "checkpoints": ["Alice checkpoint"]
    }
    """
    bob_reply = """
    {
      "answer": "Bob answer",
      "next_task": "Bob task",
      "exercise": "Bob exercise",
      "checkpoints": ["Bob checkpoint"]
    }
    """
    raw_model_reply = """
    {
      "answer": "Current answer",
      "next_task": "Current task",
      "exercise": "Current exercise",
      "checkpoints": ["Current checkpoint"]
    }
    """
    save_conversation("alice", "Alice previous question", alice_reply)
    save_conversation("bob", "Bob previous question", bob_reply)
    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，确认只拼当前 user_id 的历史。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "alice",
            "message": "Continue as Alice.",
        },
    )

    assert response.status_code == 200

    prompt_text = "\n".join(
        str(message["content"])
        for message in captured_messages
    )
    assert "Alice previous question" in prompt_text
    assert "Alice answer" in prompt_text
    assert "Bob previous question" not in prompt_text
    assert "Bob answer" not in prompt_text


def test_chat_history_prompt_respects_recent_history_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "Current answer",
      "next_task": "Current task",
      "exercise": "Current exercise",
      "checkpoints": ["Current checkpoint"]
    }
    """

    for index in range(1, RECENT_HISTORY_LIMIT + 2):
        reply_json = f"""
        {{
          "answer": "History answer {index}",
          "next_task": "Task {index}",
          "exercise": "Exercise {index}",
          "checkpoints": ["Checkpoint {index}"]
        }}
        """
        save_conversation("default", f"History question {index}", reply_json)

    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，确认只带最近 RECENT_HISTORY_LIMIT 条历史。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Current question after many turns.",
        },
    )

    assert response.status_code == 200

    history_user_messages = [
        message["content"]
        for message in captured_messages
        if message["role"] == "user"
        and str(message["content"]).startswith("History question")
    ]
    assert history_user_messages == [
        f"History question {index}"
        for index in range(2, RECENT_HISTORY_LIMIT + 2)
    ]
    assert "History question 1" not in history_user_messages


def test_chat_skips_bad_history_reply_json_without_crashing(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    raw_model_reply = """
    {
      "answer": "Current answer",
      "next_task": "Current task",
      "exercise": "Current exercise",
      "checkpoints": ["Current checkpoint"]
    }
    """
    save_conversation("default", "Bad history question", "not valid json")
    captured_messages = []

    def fake_call_model(messages):
        # 捕获 prompt，确认坏历史只跳过 assistant answer，不让接口崩溃。
        captured_messages.extend(messages)
        return raw_model_reply

    monkeypatch.setattr(
        chat_route.tutor_agent_service,
        "_call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={
            "user_id": "default",
            "message": "Continue after bad history.",
        },
    )

    assert response.status_code == 200

    role_and_content = [
        (message["role"], message["content"])
        for message in captured_messages
    ]
    assert role_and_content[1:] == [
        ("user", "Bad history question"),
        ("user", "Continue after bad history."),
    ]


def test_get_conversations_returns_recent_history_for_user(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    first_reply = """
    {
      "answer": "First answer",
      "next_task": "First task",
      "exercise": "First exercise",
      "checkpoints": ["First checkpoint"]
    }
    """
    second_reply = """
    {
      "answer": "Second answer",
      "next_task": "Second task",
      "exercise": "Second exercise",
      "checkpoints": ["Second checkpoint"]
    }
    """
    bob_reply = """
    {
      "answer": "Bob answer",
      "next_task": "Bob task",
      "exercise": "Bob exercise",
      "checkpoints": ["Bob checkpoint"]
    }
    """

    save_conversation("alice", "first question", first_reply)
    second_id = save_conversation("alice", "second question", second_reply)
    save_conversation("bob", "bob question", bob_reply)

    response = client.get("/conversations/alice")

    assert response.status_code == 200
    body = response.json()

    assert body["user_id"] == "alice"
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == second_id
    assert body["items"][0]["message"] == "second question"
    assert body["items"][0]["reply"]["answer"] == "Second answer"
    assert body["items"][1]["message"] == "first question"
    assert all(item["message"] != "bob question" for item in body["items"])


def test_get_conversations_respects_custom_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    reply_json = """
    {
      "answer": "Answer",
      "next_task": "Task",
      "exercise": "Exercise",
      "checkpoints": ["Checkpoint"]
    }
    """

    save_conversation("alice", "first question", reply_json)
    save_conversation("alice", "second question", reply_json)
    third_id = save_conversation("alice", "third question", reply_json)

    response = client.get("/conversations/alice?limit=2")

    assert response.status_code == 200
    body = response.json()

    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == third_id
    assert body["items"][0]["message"] == "third question"
    assert body["items"][1]["message"] == "second question"


def test_get_conversations_rejects_invalid_limit():
    response = client.get("/conversations/alice?limit=0")

    assert response.status_code == 422
