"""Minimal journal API contract tests."""

import pytest

from fastapi.testclient import TestClient
from app.api.routes import journal as journal_route
from app.main import app


client = TestClient(app)


def test_journal_entries_are_served_without_api_prefix(monkeypatch):
    monkeypatch.setattr(journal_route, "list_journal_entries", lambda **_: [])

    response = client.get("/journal/entries")

    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert client.get("/api/journal/entries").status_code == 404

@pytest.fixture(autouse=True)
def isolated_journal_database(tmp_path, monkeypatch):
    from app.db import database

    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_journal_api_crud_and_query_parameters():
    create = client.post(
        "/journal/entries",
        json={
            "title": "API note",
            "content": "entry body",
            "tags": "python,api",
            "entry_date": "2026-07-28",
        },
    )
    assert create.status_code == 201
    entry = create.json()
    entry_id = entry["id"]
    assert entry["content"] == "entry body"

    fetched = client.get(f"/journal/entries/{entry_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == entry_id

    listed = client.get("/journal/entries", params={"date": "2026-07-28", "tag": "python", "limit": 1})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [entry_id]

    updated = client.put(
        f"/journal/entries/{entry_id}",
        json={"title": "Updated API note", "content": "updated", "tags": "tests"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated API note"

    deleted = client.delete(f"/journal/entries/{entry_id}")
    assert deleted.status_code == 204
    assert client.get(f"/journal/entries/{entry_id}").status_code == 404


def test_journal_api_rejects_invalid_input_and_query_bounds():
    assert client.post("/journal/entries", json={"title": "", "content": "body"}).status_code == 422
    assert client.post("/journal/entries", json={"title": "valid", "content": "x" * 50001}).status_code == 422
    assert client.get("/journal/entries", params={"limit": 0}).status_code == 422
    assert client.get("/journal/entries", params={"limit": 201}).status_code == 422
    assert client.get("/journal/entries/does-not-exist").status_code == 422


@pytest.mark.xfail(strict=True, reason="CreateJournalEntryRequest currently accepts arbitrary entry_date strings")
def test_journal_api_rejects_invalid_date_format():
    assert client.post(
        "/journal/entries",
        json={"title": "invalid date", "content": "body", "entry_date": "not-a-date"},
    ).status_code == 422

@pytest.mark.xfail(strict=True, reason="CreateJournalEntryRequest currently permits an empty content string")
def test_journal_api_rejects_empty_content():
    assert client.post(
        "/journal/entries",
        json={"title": "empty body", "content": ""},
    ).status_code == 422