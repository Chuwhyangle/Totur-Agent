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


@pytest.mark.parametrize(
    "invalid_element",
    ["not-a-number", None, True, float("nan"), float("inf"), float("-inf")],
)
def test_invalid_embedding_element_fails_before_repository_rebuild(
    tmp_path, invalid_element
):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = RecordingRepository()
    embedding = FakeEmbedding(
        responses=[[[1.0, invalid_element, 3.0]]]
    )

    with pytest.raises(ValueError, match=r"vector 0 element 1"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
            )
        )

    assert repository.calls == []


def test_real_numeric_scalar_types_are_accepted(tmp_path):
    import numpy as np

    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = RecordingRepository()
    embedding = FakeEmbedding(
        responses=[[[np.float32(1.0), np.float64(2.0), np.int32(3)]]]
    )

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            embedding_client=embedding,
        )
    )

    assert result.indexed_count == 1
    assert len(repository.calls) == 1


def test_later_provider_failure_does_not_call_destructive_repository_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    write_corpus_file(tmp_path, "docs/b.md", "b")

    class FailsOnSecondBatch:
        def __init__(self):
            self.calls = []

        def embed_texts(self, texts):
            self.calls.append(list(texts))
            if len(self.calls) == 2:
                raise RuntimeError("provider down")
            return [[1.0, 2.0, 3.0] for _ in texts]

    class DestructiveRepository:
        def __init__(self):
            self.contents = ["existing index"]
            self.rebuild_calls = 0

        def rebuild(self, chunks, embeddings):
            self.rebuild_calls += 1
            self.contents.clear()
            return len(chunks)

    repository = DestructiveRepository()
    embedding = FailsOnSecondBatch()

    with pytest.raises(RuntimeError, match="provider down"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
                batch_size=1,
            )
        )

    assert len(embedding.calls) == 2
    assert repository.rebuild_calls == 0
    assert repository.contents == ["existing index"]


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


def test_rebuilding_same_stable_inputs_ignores_different_build_times(
    tmp_path, monkeypatch
):
    write_corpus_file(tmp_path, "docs/b.md", "b")
    write_corpus_file(tmp_path, "docs/a.md", "a")

    import app.services.knowledge_index_builder as builder_module

    build_times = iter(
        (
            datetime.fromisoformat("2026-07-13T00:00:00+00:00"),
            datetime.fromisoformat("2026-07-14T00:00:00+00:00"),
        )
    )

    class SequencedDateTime:
        @classmethod
        def now(cls, timezone):
            value = next(build_times)
            assert value.tzinfo == timezone
            return value

    monkeypatch.setattr(builder_module, "datetime", SequencedDateTime)

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

    assert first.manifest.built_at != second.manifest.built_at
    assert first.manifest.stable_payload() == second.manifest.stable_payload()
    assert first.manifest.fingerprint == second.manifest.fingerprint


def test_multiple_source_dirs_are_globally_sorted_and_rebuilt_together(tmp_path):
    write_corpus_file(tmp_path, "docs/local.md", "local")
    write_corpus_file(tmp_path, "corpus/self-llm/docs/guide.md", "external")
    repository = RecordingRepository()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            source_dir=None,
            source_dirs=(Path("docs"), Path("corpus/self-llm/docs")),
            repository=repository,
        )
    )

    chunks, _ = repository.calls[0]
    assert [chunk.source for chunk in chunks] == [
        "corpus/self-llm/docs/guide.md",
        "docs/local.md",
    ]
    assert [item.path for item in result.manifest.files] == [
        "corpus/self-llm/docs/guide.md",
        "docs/local.md",
    ]


def test_single_source_dir_keyword_remains_compatible(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    assert build_knowledge_index(**build_kwargs(tmp_path)).indexed_count == 1


def test_formal_rag_sources_include_local_and_self_llm_corpus():
    from app.services.rag_settings import KNOWLEDGE_SOURCE_DIRS

    assert KNOWLEDGE_SOURCE_DIRS == ("docs", "corpus/self-llm/docs")

class IncrementalRepository:
    """Small in-memory repository used to verify mutation boundaries."""

    def __init__(self):
        self.chunks = {}
        self.calls = []

    def rebuild(self, chunks, embeddings):
        self.calls.append(("rebuild", [chunk.chunk_id for chunk in chunks]))
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}
        return len(chunks)

    def upsert(self, chunks, embeddings):
        self.calls.append(("upsert", [chunk.chunk_id for chunk in chunks]))
        self.chunks.update({chunk.chunk_id: chunk for chunk in chunks})
        return len(chunks)

    def delete(self, ids):
        self.calls.append(("delete", list(ids)))
        for chunk_id in ids:
            self.chunks.pop(chunk_id, None)
        return len(ids)

    def count(self):
        return len(self.chunks)


def test_unchanged_manifest_skips_chunking_embedding_and_repository_mutation(
    tmp_path, monkeypatch
):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    repository.calls.clear()
    embedding = FakeEmbedding()

    import app.services.knowledge_index_builder as builder_module

    def forbidden_chunk(*args):
        raise AssertionError("unchanged files must not be chunked")

    monkeypatch.setattr(builder_module, "chunk_markdown", forbidden_chunk)
    second = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            embedding_client=embedding,
            previous_manifest=first.manifest,
        )
    )

    assert second.mode == "unchanged"
    assert second.manifest is first.manifest
    assert embedding.calls == []
    assert repository.calls == []


def test_incremental_build_embeds_and_upserts_only_added_file(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    write_corpus_file(tmp_path, "docs/b.md", "b")
    repository.calls.clear()
    embedding = FakeEmbedding()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            embedding_client=embedding,
            previous_manifest=first.manifest,
        )
    )

    assert embedding.calls == [["b"]]
    assert repository.calls == [("upsert", ["docs/b.md#0"])]
    assert result.mode == "incremental"
    assert result.updated_count == 1
    assert result.deleted_count == 0
    assert result.indexed_count == 2


def test_modified_file_replaces_chunks_and_deletes_only_stale_tail(
    tmp_path, monkeypatch
):
    import app.services.knowledge_index_builder as builder_module

    def split_chunks(text, source, chunk_size, chunk_overlap):
        return [
            KnowledgeChunk(part, source, "", index)
            for index, part in enumerate(text.split("|"))
        ]

    monkeypatch.setattr(builder_module, "chunk_markdown", split_chunks)
    write_corpus_file(tmp_path, "docs/a.md", "old-0|old-1|old-2")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    write_corpus_file(tmp_path, "docs/a.md", "new-0")
    repository.calls.clear()
    embedding = FakeEmbedding()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            embedding_client=embedding,
            previous_manifest=first.manifest,
        )
    )

    assert embedding.calls == [["new-0"]]
    assert repository.calls == [
        ("upsert", ["docs/a.md#0"]),
        ("delete", ["docs/a.md#1", "docs/a.md#2"]),
    ]
    assert result.updated_count == 1
    assert result.deleted_count == 2
    assert set(repository.chunks) == {"docs/a.md#0"}


def test_removed_file_deletes_ids_from_old_manifest_without_embedding(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    write_corpus_file(tmp_path, "docs/b.md", "b")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    (tmp_path / "docs/b.md").unlink()
    repository.calls.clear()
    embedding = FakeEmbedding()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            embedding_client=embedding,
            previous_manifest=first.manifest,
        )
    )

    assert embedding.calls == []
    assert repository.calls == [("delete", ["docs/b.md#0"])]
    assert result.deleted_count == 1
    assert result.indexed_count == 1


def test_changed_index_configuration_forces_full_rebuild(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    repository.calls.clear()

    result = build_knowledge_index(
        **build_kwargs(
            tmp_path,
            repository=repository,
            previous_manifest=first.manifest,
            chunk_size=256,
        )
    )

    assert repository.calls == [("rebuild", ["docs/a.md#0"])]
    assert result.mode == "full"


def test_incremental_dimension_mismatch_fails_before_mutation(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    repository = IncrementalRepository()
    first = build_knowledge_index(**build_kwargs(tmp_path, repository=repository))
    write_corpus_file(tmp_path, "docs/a.md", "changed")
    repository.calls.clear()
    embedding = FakeEmbedding(responses=[[[1.0, 2.0]]])

    with pytest.raises(ValueError, match="dimension"):
        build_knowledge_index(
            **build_kwargs(
                tmp_path,
                repository=repository,
                embedding_client=embedding,
                previous_manifest=first.manifest,
            )
        )

    assert repository.calls == []
