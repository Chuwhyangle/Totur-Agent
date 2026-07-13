"""FR5.6 frozen-corpus and isolated-evaluation tests."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import chromadb

from app.clients.embedding_client import EmbeddingError
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.index_manifest import ManifestError
from app.services.retrieval_eval import load_eval_cases
from scripts import run_retrieval_eval
from scripts.run_retrieval_eval import (
    attach_manifest_summary,
    build_frozen_evaluation_index,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_ROOT = PROJECT_ROOT / "tests" / "data" / "corpus"
EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"
APPROVED_MARKDOWN_FILES = {
    "docs/agent-architecture.md",
    "docs/ai-collaboration-guide.md",
    "docs/api-design.md",
    "docs/data-design.md",
    "docs/frontend-quest-progress.md",
    "docs/main-quest-progress.md",
    "docs/memory-and-multi-turn-plan.md",
    "docs/requirements.md",
    "docs/superpowers/plans/2026-07-05-interview-jd-search-tool.md",
    "docs/superpowers/plans/2026-07-05-interview-jd-storage-foundation.md",
    "docs/superpowers/plans/2026-07-05-score-jd-skill-fit.md",
    "docs/superpowers/specs/2026-06-30-tutor-agent-api-design.md",
    "docs/superpowers/specs/2026-07-04-technical-interview-tool-calling-design.md",
    "docs/superpowers/specs/2026-07-05-score-jd-skill-fit-design.md",
    "docs/superpowers/specs/2026-07-13-v0.5-frozen-corpus-index-manifest-design.md",
    "docs/tools/chat-interview-jd-tool-calling.md",
    "docs/tools/interview-jd-search-tool-spec.md",
    "docs/tools/score-jd-skill-fit-tool-spec.md",
    "docs/training-plan.md",
    "docs/v0.2-retrospective.md",
    "docs/v0.2_Task_list.md",
    "docs/v0.3 RAG设计文档.md",
    "docs/v0.3-0.5 RAG.md",
    "docs/v0.3-rag-progress.md",
    "docs/v0.4-rag-progress.md",
}


def test_frozen_corpus_matches_approved_inventory_and_eval_sources():
    markdown_files = sorted((FROZEN_ROOT / "docs").rglob("*.md"))
    frozen_sources = {
        path.relative_to(FROZEN_ROOT).as_posix() for path in markdown_files
    }
    expected_sources = {
        source
        for case in load_eval_cases(EVAL_FILE)
        for source in case.expected_sources
    }
    assert frozen_sources == APPROVED_MARKDOWN_FILES
    assert expected_sources <= frozen_sources


class FakeEmbeddingClient:
    """Deterministic offline embedding provider for frozen-index tests."""

    config = type("Config", (), {"model": "fake-model"})()

    def embed_texts(self, texts):
        return [[float(len(text)), 1.0, 0.0] for text in texts]


def _build_fake_frozen_result(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text(
        "# Note\nfrozen",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(client=chromadb.EphemeralClient())
    result = build_frozen_evaluation_index(
        corpus_root=tmp_path,
        repository=repository,
        embedding_client=FakeEmbeddingClient(),
    )
    return repository, result


def test_frozen_build_uses_injected_ephemeral_repository(tmp_path):
    repository, result = _build_fake_frozen_result(tmp_path)

    assert repository.count() == result.indexed_count == 1
    assert result.manifest.corpus_root == "tests/data/corpus"
    assert result.manifest.files[0].path == "docs/note.md"


def test_attach_manifest_summary_adds_traceability(tmp_path):
    _, result = _build_fake_frozen_result(tmp_path)
    summary = {"metrics": {}, "results": []}

    attach_manifest_summary(summary, result.manifest)

    trace = summary["index_manifest"]
    assert trace["fingerprint"].startswith("sha256:")
    assert trace == {
        "fingerprint": result.manifest.fingerprint,
        "corpus": "tests/data/corpus",
        "files": 1,
        "chunks": 1,
        "embedding_model": "fake-model",
        "embedding_dimensions": 3,
    }


def test_cli_defaults_to_frozen_ephemeral_index_without_persistent_access(
    monkeypatch,
    tmp_path,
    capsys,
):
    _, result = _build_fake_frozen_result(tmp_path)
    ephemeral_client = object()
    observed = {}

    class FakeRepository:
        def __init__(self, client=None):
            assert client is ephemeral_client, "default evaluation must inject EphemeralClient"
            observed["repository"] = self

    def fake_build(**kwargs):
        observed["build"] = kwargs
        return result

    monkeypatch.setattr(run_retrieval_eval.chromadb, "EphemeralClient", lambda: ephemeral_client)
    monkeypatch.setattr(run_retrieval_eval, "KnowledgeRepository", FakeRepository)
    monkeypatch.setattr(run_retrieval_eval, "build_frozen_evaluation_index", fake_build)
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_embedding_config",
        lambda: SimpleNamespace(model="fake-model"),
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "EmbeddingClient",
        lambda config: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(run_retrieval_eval, "load_eval_cases", lambda path: [])
    monkeypatch.setattr(
        run_retrieval_eval,
        "evaluate_cases",
        lambda **kwargs: {"metrics": {}, "results": []},
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "_run_manual_cosine_check",
        lambda **kwargs: {"status": "skipped"},
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_manifest",
        lambda path: (_ for _ in ()).throw(
            AssertionError("default evaluation must not read the persistent Manifest")
        ),
    )
    monkeypatch.setattr(sys, "argv", ["run_retrieval_eval.py", "--json"])

    assert run_retrieval_eval.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert observed["build"]["corpus_root"] == run_retrieval_eval.DEFAULT_CORPUS_ROOT
    assert observed["build"]["repository"] is observed["repository"]
    assert payload["index_manifest"]["fingerprint"] == result.manifest.fingerprint
    assert payload["index_manifest"]["corpus"] == "tests/data/corpus"


def test_cli_uses_persistent_index_only_when_explicitly_requested(
    monkeypatch,
    tmp_path,
    capsys,
):
    _, result = _build_fake_frozen_result(tmp_path)
    observed = {}

    class ExistingRepository:
        def __init__(self, client=None):
            assert client is None
            observed["repository"] = self

        def count(self):
            return 1

    monkeypatch.setattr(
        run_retrieval_eval.chromadb,
        "EphemeralClient",
        lambda: (_ for _ in ()).throw(
            AssertionError("existing-index mode must not create EphemeralClient")
        ),
    )
    monkeypatch.setattr(run_retrieval_eval, "KnowledgeRepository", ExistingRepository)
    monkeypatch.setattr(
        run_retrieval_eval,
        "build_frozen_evaluation_index",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("existing-index mode must not rebuild frozen corpus")
        ),
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_manifest",
        lambda path: result.manifest,
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_embedding_config",
        lambda: SimpleNamespace(model="fake-model"),
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "EmbeddingClient",
        lambda config: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(run_retrieval_eval, "load_eval_cases", lambda path: [])
    monkeypatch.setattr(
        run_retrieval_eval,
        "evaluate_cases",
        lambda **kwargs: {"metrics": {}, "results": []},
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "_run_manual_cosine_check",
        lambda **kwargs: {"status": "skipped"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_retrieval_eval.py", "--use-existing-index", "--json"],
    )

    assert run_retrieval_eval.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["index_manifest"]["fingerprint"] == result.manifest.fingerprint
    assert "repository" in observed


def test_cli_reports_frozen_build_and_manifest_errors_without_traceback(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_embedding_config",
        lambda: SimpleNamespace(model="fake-model"),
    )
    monkeypatch.setattr(
        run_retrieval_eval,
        "EmbeddingClient",
        lambda config: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(run_retrieval_eval, "load_eval_cases", lambda path: [])
    monkeypatch.setattr(
        run_retrieval_eval,
        "build_frozen_evaluation_index",
        lambda **kwargs: (_ for _ in ()).throw(EmbeddingError("provider unavailable")),
    )
    monkeypatch.setattr(sys, "argv", ["run_retrieval_eval.py", "--json"])

    assert run_retrieval_eval.main() == 1
    captured = capsys.readouterr()
    assert "provider unavailable" in captured.err
    assert "Traceback" not in captured.err

    class ExistingRepository:
        def count(self):
            return 1

    monkeypatch.setattr(run_retrieval_eval, "KnowledgeRepository", ExistingRepository)
    monkeypatch.setattr(
        run_retrieval_eval,
        "load_manifest",
        lambda path: (_ for _ in ()).throw(ManifestError("invalid Manifest")),
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_retrieval_eval.py", "--use-existing-index", "--json"],
    )

    assert run_retrieval_eval.main() == 1
    captured = capsys.readouterr()
    assert "invalid Manifest" in captured.err
    assert "Traceback" not in captured.err
