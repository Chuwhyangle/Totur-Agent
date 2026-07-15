import pytest

from app.services.external_corpus_importer import (
    GitTreeEntry,
    build_path_mapping,
    import_corpus,
    normalize_git_path,
)


def test_normalize_git_path_handles_backslash_invalid_suffix_and_reserved_name():
    assert normalize_git_path(
        r"models_ascend/qwen3.5\3.6/CON.md"
    ) == "docs/models_ascend/qwen3.5/3.6/_CON.md"
    assert normalize_git_path("folder/hello. /readme.md") == "docs/folder/hello/readme.md"


def test_normalize_git_path_rejects_absolute_and_parent_paths():
    for value in ("/root.md", r"C:\root.md", "../root.md", "a/../../root.md", ""):
        with pytest.raises(ValueError):
            normalize_git_path(value)


def test_mapping_disambiguates_casefold_collision_deterministically():
    paths = ["docs/Readme.md", "docs/readme.md"]
    first = build_path_mapping(paths)
    second = build_path_mapping(list(reversed(paths)))
    assert first == second
    assert len(set(first.values())) == 2
    assert all("--" in value for value in first.values())

def test_import_exports_only_markdown_and_writes_manifest(tmp_path):
    import hashlib
    import json

    result = import_corpus(
        project_root=tmp_path,
        commit_sha="a" * 40,
        repository_url="https://github.com/datawhalechina/self-llm.git",
        license_name="Apache-2.0",
        license_bytes=b"Apache License",
        entries=[
            GitTreeEntry("README.md", b"# readme\n"),
            GitTreeEntry(r"models_ascend/qwen3.5\3.6/guide.md", b"guide\n"),
            GitTreeEntry("image.png", b"png"),
            GitTreeEntry("script.py", b"print(1)"),
            GitTreeEntry("book.ipynb", b"{}"),
            GitTreeEntry("dataset.json", b"{}"),
        ],
    )

    target = tmp_path / "corpus/self-llm"
    docs = sorted((target / "docs").rglob("*.md"))
    assert len(docs) == 2
    assert (
        target / "docs/models_ascend/qwen3.5/3.6/guide.md"
    ).read_bytes() == b"guide\n"
    assert (target / "LICENSE").read_bytes() == b"Apache License"
    assert result.target_path == target
    assert result.manifest["commit_sha"] == "a" * 40
    assert result.manifest["markdown_file_count"] == 2
    assert result.manifest["files"][0] == {
        "original_path": "README.md",
        "normalized_path": "docs/README.md",
        "content_sha256": "sha256:" + hashlib.sha256(b"# readme\n").hexdigest(),
        "byte_count": 9,
    }
    assert json.loads((target / "corpus_manifest.json").read_text("utf-8")) == result.manifest


def test_invalid_utf8_does_not_replace_existing_target(tmp_path):
    target = tmp_path / "corpus/self-llm/docs/old.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")

    with pytest.raises(UnicodeDecodeError):
        import_corpus(
            project_root=tmp_path,
            commit_sha="b" * 40,
            repository_url="url",
            license_name="Apache-2.0",
            license_bytes=b"license",
            entries=[GitTreeEntry("bad.md", b"\xff")],
        )

    assert target.read_bytes() == b"old"
    assert not list((tmp_path / "corpus").glob(".self-llm-staging-*"))


def test_same_input_has_same_fingerprint(tmp_path):
    kwargs = dict(
        commit_sha="c" * 40,
        repository_url="url",
        license_name="Apache-2.0",
        license_bytes=b"license",
        entries=[GitTreeEntry("b.md", b"b"), GitTreeEntry("a.md", b"a")],
    )

    first = import_corpus(project_root=tmp_path / "one", **kwargs)
    second = import_corpus(project_root=tmp_path / "two", **kwargs)

    assert first.manifest["fingerprint"] == second.manifest["fingerprint"]
    assert first.manifest["files"] == second.manifest["files"]


def test_replace_failure_restores_existing_target_and_removes_staging(
    tmp_path, monkeypatch
):
    import app.services.external_corpus_importer as importer_module

    target = tmp_path / "corpus/self-llm"
    old = target / "docs/old.md"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    real_move = importer_module.shutil.move
    calls = []

    def fail_second_move(source, destination):
        calls.append((source, destination))
        if len(calls) == 2:
            raise OSError("replace failed")
        return real_move(source, destination)

    monkeypatch.setattr(importer_module.shutil, "move", fail_second_move)

    with pytest.raises(OSError, match="replace failed"):
        import_corpus(
            project_root=tmp_path,
            commit_sha="e" * 40,
            repository_url="url",
            license_name="Apache-2.0",
            license_bytes=b"license",
            entries=[GitTreeEntry("new.md", b"new")],
        )

    assert old.read_bytes() == b"old"
    assert not list((tmp_path / "corpus").glob(".self-llm-staging-*"))
    assert not list((tmp_path / "corpus").glob(".self-llm-backup-*"))
