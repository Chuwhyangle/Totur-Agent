import importlib


def test_cli_fetches_ref_resolves_commit_and_imports_tree(tmp_path, monkeypatch, capsys):
    cli = importlib.import_module("scripts.import_self_llm_corpus")
    (tmp_path / "external/self-llm.git").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(
        cli,
        "run_git",
        lambda repo, *args: calls.append((repo, args)) or b"x",
    )
    monkeypatch.setattr(cli, "resolve_commit", lambda repo, ref: "d" * 40)
    monkeypatch.setattr(cli, "read_tree_entries", lambda repo, commit: [])
    monkeypatch.setattr(cli, "read_license", lambda repo, commit: b"license")
    monkeypatch.setattr(
        cli,
        "import_corpus",
        lambda **kwargs: type(
            "Result",
            (),
            {
                "target_path": tmp_path / "corpus/self-llm",
                "manifest": {
                    "markdown_file_count": 0,
                    "commit_sha": "d" * 40,
                },
            },
        )(),
    )

    assert cli.main(
        ["--project-root", str(tmp_path), "--ref", "refs/heads/main"]
    ) == 0
    assert any("fetch" in args for _, args in calls)
    assert "commit=" + "d" * 40 in capsys.readouterr().out


def test_cli_returns_nonzero_when_git_fails(tmp_path, monkeypatch):
    cli = importlib.import_module("scripts.import_self_llm_corpus")
    monkeypatch.setattr(
        cli,
        "ensure_repository",
        lambda *args: (_ for _ in ()).throw(RuntimeError("git down")),
    )

    assert cli.main(["--project-root", str(tmp_path), "--ref", "main"]) == 1


def test_read_tree_entries_decodes_utf8_and_filters_non_markdown(monkeypatch, tmp_path):
    cli = importlib.import_module("scripts.import_self_llm_corpus")
    raw = (
        b"100644 blob " + b"a" * 40 + b"\tREADME.md\0"
        + b"100644 blob " + b"b" * 40 + b"\timage.png\0"
        + b"100644 tree " + b"c" * 40 + b"\tdirectory\0"
    )
    monkeypatch.setattr(cli, "run_git", lambda repo, *args: raw)

    assert cli.read_tree_entries(tmp_path / "repo", "d" * 40) == [
        ("README.md", "a" * 40)
    ]