"""Tests for the deterministic shared knowledge index builder."""

from datetime import datetime, timedelta
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.services.knowledge_chunker import KnowledgeChunk
from app.services.knowledge_index_builder import (
    EmbeddingProvider,
    IndexBuildResult,
    IndexRepository,
    build_knowledge_index,
)


class FakeEmbedding:
    """Deterministic, network-free embedding provider."""

    def __init__(self, responses=None, error=None):
        self.calls = []
        self.responses = list(responses or [])
        self.error = error

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return [[1.0, 2.0, 3.0] for _ in texts]


class RecordingRepository:
    """Records the exact rebuild input and returns a configurable count."""

    def __init__(self, return_count=None):
        self.calls = []
        self.return_count = return_count

    def rebuild(self, chunks, embeddings) -> int:
        self.calls.append((list(chunks), [list(vector) for vector in embeddings]))
        if self.return_count is not None:
            return self.return_count
        return len(chunks)


def write_corpus_file(root: Path, relative_path: str, content: str | bytes) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def build_kwargs(root: Path, **overrides):
    kwargs = {
        "corpus_root": root,
        "source_dir": Path("docs"),
        "corpus_label": "frozen-corpus",
        "repository": RecordingRepository(),
        "embedding_client": FakeEmbedding(),
        "embedding_model": "fake-model",
        "chunk_size": 512,
        "chunk_overlap": 50,
        "batch_size": 32,
        "collection_name": "learning_notes",
    }
    kwargs.update(overrides)
    return kwargs


def test_recursive_markdown_files_are_sorted_and_report_relative_sources(tmp_path):
    write_corpus_file(tmp_path, "docs/z.md", "z document")
    write_corpus_file(tmp_path, "docs/nested/a.md", "a document")
    write_corpus_file(tmp_path, "docs/ignored.txt", "not markdown")
    progress = []
    repository = RecordingRepository()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            progress=lambda source, count: progress.append((source, count)),
        )
    )

    chunks, embeddings = repository.calls[0]
    assert [chunk.source for chunk in chunks] == [
        "docs/nested/a.md",
        "docs/z.md",
    ]
    assert [item.path for item in result.manifest.files] == [
        "docs/nested/a.md",
        "docs/z.md",
    ]
    assert progress == [
        ("docs/nested/a.md", 1),
        ("docs/z.md", 1),
    ]
    assert [item.chunk_count for item in result.manifest.files] == [1, 1]
    assert result.manifest.chunk_count == len(chunks) == len(embeddings) == 2


def test_chunking_receives_source_and_requested_window_settings(tmp_path, monkeypatch):
    write_corpus_file(tmp_path, "docs/a.md", "body")
    calls = []

    def fake_chunk_markdown(text, source, chunk_size, chunk_overlap):
        calls.append((text, source, chunk_size, chunk_overlap))
        return [KnowledgeChunk("chunk", source, "", 0)]

    import app.services.knowledge_index_builder as builder_module

    monkeypatch.setattr(builder_module, "chunk_markdown", fake_chunk_markdown)

    build_knowledge_index(
        **build_kwargs(tmp_path, chunk_size=17, chunk_overlap=3)
    )

    assert calls == [("body", "docs/a.md", 17, 3)]


def test_embeddings_are_requested_in_configured_batch_sizes(tmp_path):
    for name in ("c", "a", "e", "b", "d"):
        write_corpus_file(tmp_path, f"docs/{name}.md", name)
    embedding = FakeEmbedding()
    repository = RecordingRepository()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            embedding_client=embedding,
            repository=repository,
            batch_size=2,
        )
    )

    assert [len(call) for call in embedding.calls] == [2, 2, 1]
    assert [text for call in embedding.calls for text in call] == [
        "a",
        "b",
        "c",
        "d",
        "e",
    ]
    assert result.indexed_count == 5
    assert len(repository.calls[0][1]) == 5


def test_empty_corpus_fails_explicitly(tmp_path):
    write_corpus_file(tmp_path, "docs/readme.txt", "not markdown")

    with pytest.raises(ValueError, match="markdown"):
        build_knowledge_index(**build_kwargs(tmp_path))


def test_all_zero_chunk_corpus_fails_without_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/empty.md", "# Heading only\n")
    repository = RecordingRepository()
    embedding = FakeEmbedding()

    with pytest.raises(ValueError, match="chunk"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
            )
        )

    assert embedding.calls == []
    assert repository.calls == []


def test_empty_chunk_file_is_recorded_when_other_files_have_chunks(tmp_path):
    write_corpus_file(tmp_path, "docs/empty.md", "# Heading only\n")
    write_corpus_file(tmp_path, "docs/full.md", "# Heading\nBody")
    progress = []
    repository = RecordingRepository()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            progress=lambda source, count: progress.append((source, count)),
        )
    )

    assert progress == [("docs/empty.md", 0), ("docs/full.md", 1)]
    assert [(item.path, item.chunk_count) for item in result.manifest.files] == [
        ("docs/empty.md", 0),
        ("docs/full.md", 1),
    ]
    assert result.manifest.chunk_count == result.indexed_count == 1


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"batch_size": 0}, "batch_size"),
        ({"batch_size": -1}, "batch_size"),
        ({"corpus_label": ""}, "corpus_label"),
        ({"embedding_model": "   "}, "embedding_model"),
        ({"collection_name": ""}, "collection_name"),
    ],
)
def test_required_nonempty_inputs_are_validated(tmp_path, override, message):
    with pytest.raises(ValueError, match=message):
        build_knowledge_index(**build_kwargs(tmp_path, **override))


def test_embedding_count_mismatch_fails_before_repository_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    write_corpus_file(tmp_path, "docs/b.md", "b")
    repository = RecordingRepository()
    embedding = FakeEmbedding(responses=[[[1.0, 2.0, 3.0]]])

    with pytest.raises(ValueError, match="count"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
                batch_size=2,
            )
        )

    assert repository.calls == []


def test_embedding_dimension_mismatch_fails_before_repository_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    write_corpus_file(tmp_path, "docs/b.md", "b")
    repository = RecordingRepository()
    embedding = FakeEmbedding(
        responses=[[[1.0, 2.0, 3.0]], [[1.0, 2.0]]]
    )

    with pytest.raises(ValueError, match="dimension"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
                batch_size=1,
            )
        )

    assert repository.calls == []


def test_provider_failure_happens_before_repository_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = RecordingRepository()
    embedding = FakeEmbedding(error=RuntimeError("provider down"))

    with pytest.raises(RuntimeError, match="provider down"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
            )
        )

    assert repository.calls == []


def test_invalid_utf8_read_failure_happens_before_repository_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/bad.md", b"\xff\xfe")
    repository = RecordingRepository()

    with pytest.raises(UnicodeDecodeError):
        build_knowledge_index(**build_kwargs(tmp_path, repository=repository))

    assert repository.calls == []


def test_repository_count_mismatch_is_rejected(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = RecordingRepository(return_count=0)

    with pytest.raises(ValueError, match="indexed"):
        build_knowledge_index(**build_kwargs(tmp_path, repository=repository))

    assert len(repository.calls) == 1


def test_success_returns_frozen_result_and_manifest_with_utc_metadata(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            corpus_label="corpus-label",
            embedding_model="model-3d",
            collection_name="collection",
        )
    )

    assert isinstance(result, IndexBuildResult)
    assert result.manifest.schema_version == 1
    assert result.manifest.corpus_root == "corpus-label"
    assert result.manifest.embedding_model == "model-3d"
    assert result.manifest.collection_name == "collection"
    assert result.manifest.embedding_dimensions == 3
    assert result.manifest.chunk_count == result.indexed_count == 1
    built_at = datetime.fromisoformat(result.manifest.built_at)
    assert built_at.utcoffset() == timedelta(0)
    with pytest.raises(FrozenInstanceError):
        result.indexed_count = 99


def test_rebuilding_same_corpus_produces_stable_manifest_fingerprint(tmp_path):
    write_corpus_file(tmp_path, "docs/b.md", "b")
    write_corpus_file(tmp_path, "docs/a.md", "a")

    first = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            embedding_client=FakeEmbedding(),
            repository=RecordingRepository(),
        )
    )
    second = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            embedding_client=FakeEmbedding(),
            repository=RecordingRepository(),
        )
    )

    assert first.manifest.fingerprint == second.manifest.fingerprint
