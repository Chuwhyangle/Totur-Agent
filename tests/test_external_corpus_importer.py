import pytest

from app.services.external_corpus_importer import build_path_mapping, normalize_git_path


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