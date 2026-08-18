"""Journal repository tests isolated to a temporary SQLite database."""

import pytest

from app.db import database
from app.repositories import journal_repository as repository


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    database_path = tmp_path / "tutor_agent.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield database_path
    assert database_path.parent == tmp_path


def test_create_get_update_and_delete_journal_entry():
    created = repository.create_journal_entry(
        title="Day one",
        content="Learned SQLite",
        entry_date="2026-07-28",
        session_id=None,
        persona_id="journal",
        tags="python,sqlite",
    )

    fetched = repository.get_journal_entry(created.id)
    assert fetched == created

    updated = repository.update_journal_entry(
        created.id,
        title="Day one revised",
        content="Learned SQLite backup",
        tags="sqlite,backup",
        entry_date="2026-07-29",
    )
    assert updated is not None
    assert updated.title == "Day one revised"
    assert updated.content == "Learned SQLite backup"
    assert updated.tags == "sqlite,backup"
    assert updated.entry_date == "2026-07-29"
    assert updated.updated_at >= created.updated_at

    assert repository.delete_journal_entry(created.id) is True
    assert repository.get_journal_entry(created.id) is None
    assert repository.delete_journal_entry(created.id) is False


def test_list_filters_by_date_tag_and_limit():
    first = repository.create_journal_entry("A", "a", "2026-07-27", tags="python,api")
    second = repository.create_journal_entry("B", "b", "2026-07-28", tags="python,fastapi")
    repository.create_journal_entry("C", "c", "2026-07-28", tags="javascript")

    by_date = repository.list_journal_entries(date="2026-07-28")
    assert [entry.title for entry in by_date] == ["C", "B"]

    by_tag = repository.list_journal_entries(tag="python")
    assert [entry.id for entry in by_tag] == [second.id, first.id]

    limited = repository.list_journal_entries(limit=1)
    assert len(limited) == 1
    assert limited[0].title == "C"


@pytest.mark.xfail(strict=True, reason="tag filtering currently uses substring LIKE and matches api inside fastapi")
def test_list_tag_filter_matches_a_complete_comma_separated_tag():
    exact = repository.create_journal_entry("Exact", "a", "2026-07-27", tags="python,api")
    repository.create_journal_entry("Substring", "b", "2026-07-28", tags="fastapi")

    matches = repository.list_journal_entries(tag="api")

    assert [entry.id for entry in matches] == [exact.id]
