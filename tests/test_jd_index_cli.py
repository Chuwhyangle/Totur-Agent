from types import SimpleNamespace

import scripts.build_jd_index as cli


def test_cli_passes_full_and_dry_run_flags(monkeypatch, tmp_path, capsys):
    calls = {}
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_jd_dataset", lambda root: ("parent",))
    monkeypatch.setattr(
        cli,
        "load_embedding_config",
        lambda: SimpleNamespace(model="fake-model"),
    )
    monkeypatch.setattr(cli, "EmbeddingClient", lambda config: "embedding-client")
    monkeypatch.setattr(cli, "JDVectorRepository", lambda: "repository")

    def fake_build(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            mode="dry-run-full",
            parent_count=485,
            child_count=970,
            updated_parent_count=485,
            updated_child_count=970,
            deleted_parent_count=0,
            deleted_child_count=0,
            manifest=None,
        )

    monkeypatch.setattr(cli, "build_jd_index", fake_build)

    assert cli.main(["--dry-run", "--full"]) == 0
    assert calls["dry_run"] is True
    assert calls["full"] is True
    assert calls["embedding_model"] == "fake-model"
    assert calls["parents"] == ("parent",)
    output = capsys.readouterr().out
    assert "mode=dry-run-full" in output
    assert "parents=485" in output
    assert "children=970" in output
