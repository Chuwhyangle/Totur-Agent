"""Tests for server and reverse-proxy configuration."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api.routes.journal import router as journal_router
from app.config import StorageConfig, ServerConfig


def test_allowed_origins_are_trimmed_and_empty_items_are_ignored(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://example.com, http://localhost:5173,,  ",
    )

    config = ServerConfig.from_env()

    assert config.ALLOWED_ORIGINS == [
        "https://example.com",
        "http://localhost:5173",
    ]


def test_unconfigured_allowed_origins_keep_local_vite_defaults(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    config = ServerConfig.from_env()

    assert "http://localhost:5173" in config.ALLOWED_ORIGINS
    assert "http://127.0.0.1:5173" in config.ALLOWED_ORIGINS


def test_root_path_is_proxy_context_not_a_route_prefix(monkeypatch):
    monkeypatch.setenv("ROOT_PATH", " /api ")
    config = ServerConfig.from_env()
    proxy_app = FastAPI(root_path=config.ROOT_PATH)
    proxy_app.include_router(journal_router)
    journal_paths = {
        path for path in proxy_app.openapi()["paths"] if "journal" in path
    }

    assert proxy_app.root_path == "/api"
    assert "/journal/entries" in journal_paths
    assert all(not path.startswith("/api/") for path in journal_paths)


def test_data_dir_keeps_sqlite_and_chroma_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    config = StorageConfig.from_env()

    assert config.database_path == Path(tmp_path) / "tutor_agent.db"
    assert config.chroma_persist_dir == Path(tmp_path) / "chroma_db"


def test_data_dir_rejects_repository_root(monkeypatch):
    repository_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATA_DIR", str(repository_root))

    with pytest.raises(RuntimeError, match="禁止将 DATA_DIR 设置为项目目录"):
        StorageConfig.from_env()


def test_database_url_rejects_repository_database(monkeypatch):
    repository_database = Path(__file__).resolve().parents[1] / "tutor_agent.db"
    monkeypatch.setenv("DATA_DIR", str(repository_database.parent.parent))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{repository_database.as_posix()}")

    config = StorageConfig.from_env()
    with pytest.raises(RuntimeError, match="禁止使用仓库内 tutor_agent.db"):
        _ = config.database_url
