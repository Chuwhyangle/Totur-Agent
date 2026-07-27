"""Minimal journal API contract tests."""

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
