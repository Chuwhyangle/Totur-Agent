"""Tests for the save_journal_entry agent tool."""

from types import SimpleNamespace

from app.services.agent.tools import save_journal_entry as tool_module


def test_save_journal_entry_normalizes_input_and_returns_confirmation(monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=42, title=kwargs["title"], entry_date=kwargs["entry_date"], tags=kwargs["tags"])

    monkeypatch.setattr(tool_module, "create_journal_entry", fake_create)

    result = tool_module.save_journal_entry(
        title="  Daily note  ",
        content="What I learned",
        tags="  python,tests  ",
        entry_date=" 2026-07-28 ",
    )

    assert captured == {
        "title": "Daily note",
        "content": "What I learned",
        "entry_date": "2026-07-28",
        "tags": "python,tests",
    }
    assert result == {
        "ok": True,
        "id": 42,
        "title": "Daily note",
        "entry_date": "2026-07-28",
        "tags": "python,tests",
        "message": "日记已保存（id=42）：Daily note",
    }


def test_save_journal_entry_rejects_empty_title_and_non_string_content(monkeypatch):
    create = monkeypatch.setattr(tool_module, "create_journal_entry", lambda **_: None)

    empty_title = tool_module.save_journal_entry("   ", "content")
    invalid_content = tool_module.save_journal_entry("title", None)

    assert empty_title["ok"] is False
    assert empty_title["error"] == "invalid_arguments"
    assert invalid_content["ok"] is False
    assert invalid_content["error"] == "invalid_arguments"


def test_save_journal_entry_classifies_repository_failure(monkeypatch):
    def fail_create(**_kwargs):
        raise OSError("database is read-only")

    monkeypatch.setattr(tool_module, "create_journal_entry", fail_create)

    result = tool_module.save_journal_entry("title", "content")

    assert result["ok"] is False
    assert result["error"] == "save_failed"
    assert "database is read-only" in result["message"]
