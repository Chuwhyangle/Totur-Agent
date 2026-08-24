"""Workspace feature flag tests."""

from app.services.workspaces import settings


def test_workspaces_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_WORKSPACES", raising=False)
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)

    assert settings.is_workspaces_enabled() is False


def test_workspaces_accept_common_true_values(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)

    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ENABLE_WORKSPACES", value)
        assert settings.is_workspaces_enabled() is True


def test_workspaces_reject_false_and_unknown_values(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)

    for value in ("0", "false", "off", "no", "unexpected", ""):
        monkeypatch.setenv("ENABLE_WORKSPACES", value)
        assert settings.is_workspaces_enabled() is False
