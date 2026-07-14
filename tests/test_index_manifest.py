"""FR5.3 stable index Manifest tests."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest

from app.services.index_manifest import (
    CorpusFileManifest,
    IndexManifest,
    ManifestError,
    load_manifest,
    sha256_bytes,
    write_manifest,
)


def make_manifest(
    *,
    built_at="2026-07-13T00:00:00+00:00",
    corpus_root="tests/data/corpus",
    collection_name="learning_notes",
    embedding_model="fake-model",
    embedding_dimensions=3,
    chunk_size=512,
    chunk_overlap=50,
    files=None,
):
    if files is None:
        files = (
            CorpusFileManifest("docs/a.md", "a" * 64, 2),
            CorpusFileManifest("docs/b.md", "b" * 64, 1),
        )
    return IndexManifest.create(
        schema_version=1,
        collection_name=collection_name,
        built_at=built_at,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        corpus_root=corpus_root,
        files=files,
    )


def test_sha256_bytes_hashes_original_utf8_bytes():
    content = "中文\n".encode("utf-8")

    assert sha256_bytes(content) == hashlib.sha256(content).hexdigest()


def test_time_root_and_input_order_do_not_change_fingerprint():
    original = make_manifest()
    changed_time_and_root = make_manifest(
        built_at="2026-07-14T00:00:00+00:00",
        corpus_root="C:/different/machine",
    )
    reversed_file_input = make_manifest(files=tuple(reversed(original.files)))

    assert changed_time_and_root.fingerprint == original.fingerprint
    assert reversed_file_input.fingerprint == original.fingerprint
    assert [item.path for item in reversed_file_input.files] == [
        "docs/a.md",
        "docs/b.md",
    ]


def test_stable_identity_changes_when_index_inputs_change():
    original = make_manifest()
    changed_model = make_manifest(embedding_model="other-model")
    changed_dimensions = make_manifest(embedding_dimensions=4)
    changed_chunk_size = make_manifest(chunk_size=513)
    changed_file_hash = make_manifest(
        files=(
            CorpusFileManifest("docs/a.md", "c" * 64, 2),
            CorpusFileManifest("docs/b.md", "b" * 64, 1),
        )
    )

    assert changed_model.fingerprint != original.fingerprint
    assert changed_dimensions.fingerprint != original.fingerprint
    assert changed_chunk_size.fingerprint != original.fingerprint
    assert changed_file_hash.fingerprint != original.fingerprint


def test_fingerprint_uses_the_required_canonical_json():
    manifest = make_manifest(
        files=(CorpusFileManifest("docs/中文.md", "a" * 64, 1),)
    )
    stable_payload = manifest.stable_payload()
    canonical = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert manifest.fingerprint == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    assert "built_at" not in stable_payload
    assert "fingerprint" not in stable_payload
    assert "root" not in stable_payload["corpus"]


def test_to_dict_has_exact_schema_one_shape():
    raw = make_manifest().to_dict()

    assert set(raw) == {
        "schema_version",
        "fingerprint",
        "collection_name",
        "built_at",
        "embedding",
        "chunking",
        "corpus",
    }
    assert set(raw["embedding"]) == {"model", "dimensions"}
    assert set(raw["chunking"]) == {"chunk_size", "chunk_overlap"}
    assert set(raw["corpus"]) == {
        "root",
        "file_count",
        "chunk_count",
        "files",
    }
    assert set(raw["corpus"]["files"][0]) == {
        "path",
        "content_sha256",
        "chunk_count",
    }


def test_manifest_json_round_trip_creates_parent_and_replaces_target(tmp_path):
    path = tmp_path / "nested" / "index_manifest.json"
    path.parent.mkdir()
    path.write_text("stale", encoding="utf-8")
    original = make_manifest(corpus_root="语料")

    write_manifest(path, original)

    assert load_manifest(path) == original
    assert not path.with_name("index_manifest.json.tmp").exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["corpus"]["root"] == "语料"
    assert raw["corpus"]["file_count"] == 2
    assert raw["corpus"]["chunk_count"] == 3


def test_atomic_write_keeps_old_target_and_cleans_temp_when_replace_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "index_manifest.json"
    temporary = path.with_name("index_manifest.json.tmp")
    old_content = b"old manifest bytes"
    path.write_bytes(old_content)

    def fail_replace(self, target):
        assert self == temporary
        assert target == path
        raise OSError("replace blocked")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(ManifestError, match="cannot write Manifest"):
        write_manifest(path, make_manifest())

    assert path.read_bytes() == old_content
    assert not temporary.exists()


def test_write_manifest_validates_before_touching_files(tmp_path):
    path = tmp_path / "new-parent" / "index_manifest.json"
    invalid = replace(make_manifest(), fingerprint="sha256:" + "0" * 64)

    with pytest.raises(ManifestError, match="fingerprint"):
        write_manifest(path, invalid)

    assert not path.parent.exists()


def test_dataclasses_are_frozen_and_file_records_are_orderable():
    files = (
        CorpusFileManifest("docs/b.md", "b" * 64, 1),
        CorpusFileManifest("docs/a.md", "a" * 64, 2),
    )
    manifest = make_manifest(files=files)

    assert tuple(sorted(files)) == manifest.files
    assert isinstance(manifest.files, tuple)
    with pytest.raises(FrozenInstanceError):
        manifest.collection_name = "changed"
    with pytest.raises(FrozenInstanceError):
        files[0].path = "changed.md"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"collection_name": "  "}, "collection_name"),
        ({"embedding_model": ""}, "embedding model"),
        ({"embedding_dimensions": 0}, "embedding dimensions"),
        ({"chunk_size": 0}, "chunking"),
        ({"chunk_overlap": -1}, "chunking"),
        ({"chunk_overlap": 512}, "chunking"),
        ({"files": ()}, "corpus files"),
    ],
)
def test_create_rejects_invalid_manifest_level_values(changes, message):
    arguments = {
        "schema_version": 1,
        "collection_name": "learning_notes",
        "built_at": "2026-07-13T00:00:00+00:00",
        "embedding_model": "fake-model",
        "embedding_dimensions": 3,
        "chunk_size": 512,
        "chunk_overlap": 50,
        "corpus_root": "tests/data/corpus",
        "files": (CorpusFileManifest("docs/a.md", "a" * 64, 1),),
    }
    arguments.update(changes)

    with pytest.raises(ManifestError, match=message):
        IndexManifest.create(**arguments)


@pytest.mark.parametrize(
    "path",
    ["", "/absolute.md", "../outside.md", "docs/../outside.md", "docs\\a.md"],
)
def test_create_rejects_non_relative_posix_file_paths(path):
    with pytest.raises(ManifestError, match="POSIX corpus path"):
        make_manifest(files=(CorpusFileManifest(path, "a" * 64, 1),))


@pytest.mark.parametrize("content_hash", ["A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_create_rejects_hashes_that_are_not_lowercase_sha256(content_hash):
    with pytest.raises(ManifestError, match="content_sha256"):
        make_manifest(
            files=(CorpusFileManifest("docs/a.md", content_hash, 1),)
        )


def test_create_rejects_negative_file_chunk_count():
    with pytest.raises(ManifestError, match="chunk_count"):
        make_manifest(
            files=(CorpusFileManifest("docs/a.md", "a" * 64, -1),)
        )


def test_validate_rejects_unsorted_direct_instances():
    manifest = make_manifest()
    unsorted = replace(manifest, files=tuple(reversed(manifest.files)))

    with pytest.raises(ManifestError, match="sorted"):
        unsorted.validate()


@pytest.mark.parametrize(
    ("field", "declared", "message"),
    [
        ("file_count", 99, "declared file_count"),
        ("chunk_count", 99, "declared chunk_count"),
    ],
)
def test_from_dict_rejects_incorrect_declared_totals(field, declared, message):
    raw = make_manifest().to_dict()
    raw["corpus"][field] = declared

    with pytest.raises(ManifestError, match=message):
        IndexManifest.from_dict(raw)


def test_from_dict_rejects_tampered_stable_payload():
    raw = make_manifest().to_dict()
    raw["embedding"]["model"] = "tampered-model"

    with pytest.raises(ManifestError, match="fingerprint"):
        IndexManifest.from_dict(raw)


def test_load_rejects_tampered_fingerprint(tmp_path):
    path = tmp_path / "index_manifest.json"
    write_manifest(path, make_manifest())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["fingerprint"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ManifestError, match="fingerprint"):
        load_manifest(path)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {"embedding": []},
    ],
)
def test_from_dict_wraps_shape_errors_as_manifest_error(raw):
    with pytest.raises(ManifestError, match="shape"):
        IndexManifest.from_dict(raw)


def test_load_rejects_invalid_schema_with_an_explicit_error(tmp_path):
    path = tmp_path / "invalid.json"
    raw = make_manifest().to_dict()
    raw["schema_version"] = 2
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ManifestError, match="schema_version"):
        load_manifest(path)


def test_load_wraps_missing_file_invalid_json_unicode_and_root_shape(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ManifestError, match="cannot read Manifest"):
        load_manifest(missing)

    invalid_json = tmp_path / "invalid-json.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot read Manifest"):
        load_manifest(invalid_json)

    invalid_unicode = tmp_path / "invalid-unicode.json"
    invalid_unicode.write_bytes(b"\xff")
    with pytest.raises(ManifestError, match="cannot read Manifest"):
        load_manifest(invalid_unicode)

    invalid_root = tmp_path / "invalid-root.json"
    invalid_root.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError, match="JSON object"):
        load_manifest(invalid_root)
