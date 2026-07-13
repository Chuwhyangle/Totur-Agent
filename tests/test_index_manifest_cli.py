"""CLI contracts for building and inspecting the live index Manifest."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from chromadb.errors import InternalError

from app.services.index_manifest import (
    CorpusFileManifest,
    IndexManifest,
    ManifestError,
    write_manifest,
)
from app.services.knowledge_index_builder import IndexBuildResult
from app.services.rag_settings import CHROMA_PERSIST_DIR, KNOWLEDGE_SOURCE_DIR
from scripts import build_knowledge_index, show_index_manifest


def make_manifest() -> IndexManifest:
    return IndexManifest.create(
        schema_version=1,
        collection_name="learning_notes",
        built_at="2026-07-13T00:00:00+00:00",
        embedding_model="fake-model",
        embedding_dimensions=3,
        chunk_size=512,
        chunk_overlap=50,
        corpus_root="docs",
        files=(
            CorpusFileManifest("docs/a.md", "a" * 64, 2),
            CorpusFileManifest("docs/nested/b.md", "b" * 64, 1),
        ),
    )


def write_fixture(path: Path) -> IndexManifest:
    manifest = make_manifest()
    write_manifest(path, manifest)
    return manifest


def install_build_fakes(
    monkeypatch,
    *,
    result=None,
    preflight_error=None,
    repository_error=None,
):
    config = SimpleNamespace(model="fake-model")
    embedding_client = object()
    calls = {}

    class RecordingRepository:
        def __init__(self):
            self.calls = []

        def rebuild(self, chunks, embeddings):
            self.calls.append((chunks, embeddings))
            if repository_error is not None:
                raise repository_error
            return len(chunks)

    repository = RecordingRepository()
    monkeypatch.setattr(build_knowledge_index, "load_embedding_config", lambda: config)

    def make_embedding_client(*, config):
        calls["embedding_config"] = config
        return embedding_client

    def make_repository():
        calls["repository_created"] = True
        return repository

    def fake_builder(**kwargs):
        calls["builder"] = kwargs
        if preflight_error is not None:
            raise preflight_error
        indexed_count = result.indexed_count if result is not None else 1
        chunks = [object()] * indexed_count
        embeddings = [[0.0]] * indexed_count
        kwargs["repository"].rebuild(chunks, embeddings)
        return result

    monkeypatch.setattr(build_knowledge_index, "EmbeddingClient", make_embedding_client)
    monkeypatch.setattr(build_knowledge_index, "KnowledgeRepository", make_repository)
    monkeypatch.setattr(
        build_knowledge_index,
        "build_knowledge_index",
        fake_builder,
        raising=False,
    )
    return calls, config, embedding_client, repository


def test_build_cli_uses_shared_builder_and_persists_successful_manifest(
    tmp_path, monkeypatch, capsys
):
    manifest = make_manifest()
    result = IndexBuildResult(indexed_count=3, manifest=manifest)
    calls, config, embedding_client, repository = install_build_fakes(
        monkeypatch,
        result=result,
    )
    monkeypatch.setattr(build_knowledge_index, "PROJECT_ROOT", tmp_path)

    def fake_write_manifest(path, value):
        calls["write"] = (path, value)

    monkeypatch.setattr(
        build_knowledge_index,
        "write_manifest",
        fake_write_manifest,
        raising=False,
    )

    assert build_knowledge_index.main() == 0

    builder_args = calls["builder"]
    assert builder_args["corpus_root"] == tmp_path
    assert builder_args["source_dir"] == Path(KNOWLEDGE_SOURCE_DIR)
    assert builder_args["corpus_label"] == KNOWLEDGE_SOURCE_DIR
    tracking_repository = builder_args["repository"]
    assert tracking_repository is not repository
    assert tracking_repository.repository is repository
    assert tracking_repository.rebuild_attempted is True
    assert len(repository.calls) == 1
    assert builder_args["embedding_client"] is embedding_client
    assert builder_args["embedding_model"] == config.model
    assert callable(builder_args["progress"])
    assert calls["embedding_config"] is config
    assert calls["repository_created"] is True
    assert calls["write"] == (
        tmp_path / CHROMA_PERSIST_DIR / "index_manifest.json",
        manifest,
    )

    output = capsys.readouterr().out
    assert "索引构建完成" in output
    assert "files=2" in output
    assert "chunks=3" in output
    assert manifest.fingerprint in output


def test_build_cli_preserves_manifest_when_builder_fails_before_rebuild(
    tmp_path, monkeypatch, capsys
):
    manifest_path = tmp_path / CHROMA_PERSIST_DIR / "index_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    original = b"previous valid manifest"
    manifest_path.write_bytes(original)
    install_build_fakes(
        monkeypatch,
        preflight_error=RuntimeError("embedding provider failed"),
    )
    monkeypatch.setattr(build_knowledge_index, "PROJECT_ROOT", tmp_path)

    def forbidden_write(*args, **kwargs):
        raise AssertionError("Manifest writer must not run after a failed build")

    monkeypatch.setattr(
        build_knowledge_index,
        "write_manifest",
        forbidden_write,
        raising=False,
    )

    assert build_knowledge_index.main() == 1
    captured = capsys.readouterr()
    assert "构建学习笔记索引失败" in captured.err
    assert "embedding provider failed" in captured.err
    assert "索引构建完成" not in captured.out
    assert manifest_path.read_bytes() == original


def test_build_cli_invalidates_old_manifest_when_repository_rebuild_fails(
    tmp_path, monkeypatch, capsys
):
    manifest_path = tmp_path / CHROMA_PERSIST_DIR / "index_manifest.json"
    write_fixture(manifest_path)
    install_build_fakes(
        monkeypatch,
        repository_error=RuntimeError("repository rebuild failed"),
    )
    monkeypatch.setattr(build_knowledge_index, "PROJECT_ROOT", tmp_path)

    assert build_knowledge_index.main() == 1

    captured = capsys.readouterr()
    assert "repository rebuild failed" in captured.err
    assert not manifest_path.exists()
    assert show_index_manifest.main(["--path", str(manifest_path)]) == 1


def test_build_cli_invalidates_old_manifest_when_manifest_write_fails(
    tmp_path, monkeypatch, capsys
):
    manifest_path = tmp_path / CHROMA_PERSIST_DIR / "index_manifest.json"
    write_fixture(manifest_path)
    manifest = make_manifest()
    install_build_fakes(
        monkeypatch,
        result=IndexBuildResult(indexed_count=3, manifest=manifest),
    )
    monkeypatch.setattr(build_knowledge_index, "PROJECT_ROOT", tmp_path)

    def failing_write(path, value):
        raise ManifestError("cannot replace Manifest")

    monkeypatch.setattr(
        build_knowledge_index,
        "write_manifest",
        failing_write,
        raising=False,
    )

    assert build_knowledge_index.main() == 1
    captured = capsys.readouterr()
    assert "cannot replace Manifest" in captured.err
    assert "fingerprint=" not in captured.out
    assert not manifest_path.exists()
    assert show_index_manifest.main(["--path", str(manifest_path)]) == 1


def test_build_cli_catches_native_chroma_error_without_traceback(
    tmp_path, monkeypatch, capsys
):
    manifest_path = tmp_path / CHROMA_PERSIST_DIR / "index_manifest.json"
    write_fixture(manifest_path)
    install_build_fakes(
        monkeypatch,
        repository_error=InternalError("database is locked"),
    )
    monkeypatch.setattr(build_knowledge_index, "PROJECT_ROOT", tmp_path)

    assert build_knowledge_index.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "database is locked" in captured.err
    assert "Traceback" not in captured.err
    assert not manifest_path.exists()


def test_show_cli_uses_default_path_and_prints_core_summary(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "index_manifest.json"
    manifest = write_fixture(path)
    monkeypatch.setattr(show_index_manifest, "DEFAULT_MANIFEST_PATH", path)

    assert show_index_manifest.main([]) == 0

    output = capsys.readouterr().out
    assert f"fingerprint: {manifest.fingerprint}" in output
    assert "collection: learning_notes" in output
    assert "embedding_model: fake-model" in output
    assert "embedding_dimensions: 3" in output
    assert "chunk_size: 512" in output
    assert "chunk_overlap: 50" in output
    assert "files: 2" in output
    assert "chunks: 3" in output
    assert "built_at: 2026-07-13T00:00:00+00:00" in output
    assert "docs/a.md" not in output


def test_show_cli_files_prints_each_file_stat(tmp_path, capsys):
    path = tmp_path / "index_manifest.json"
    write_fixture(path)

    assert show_index_manifest.main(["--path", str(path), "--files"]) == 0

    output = capsys.readouterr().out
    assert f"- docs/a.md chunks=2 sha256={'a' * 64}" in output
    assert f"- docs/nested/b.md chunks=1 sha256={'b' * 64}" in output


def test_show_cli_json_prints_complete_valid_json(tmp_path, capsys):
    path = tmp_path / "index_manifest.json"
    manifest = write_fixture(path)

    assert show_index_manifest.main(["--path", str(path), "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == manifest.to_dict()


def test_show_cli_reports_missing_manifest(tmp_path, capsys):
    path = tmp_path / "missing.json"

    assert show_index_manifest.main(["--path", str(path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "读取索引 Manifest 失败" in captured.err
    assert str(path) in captured.err


def test_show_cli_reports_invalid_manifest(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert show_index_manifest.main(["--path", str(path), "--json"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "读取索引 Manifest 失败" in captured.err
    assert str(path) in captured.err
