from dataclasses import replace

from app.services.jd_corpus import JDChildDocument, JDParentDocument
from app.services.jd_index_builder import build_jd_index


class FakeEmbedding:
    def __init__(self):
        self.calls = []

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [[float(index + 1), 0.0, 1.0] for index, _ in enumerate(texts)]


class FakeVectorRepository:
    def __init__(self):
        self.children = {}
        self.calls = []

    def rebuild(self, children, embeddings):
        self.calls.append(("rebuild", [child.child_id for child in children]))
        self.children = {child.child_id: child for child in children}
        return len(children)

    def upsert(self, children, embeddings):
        self.calls.append(("upsert", [child.child_id for child in children]))
        self.children.update({child.child_id: child for child in children})
        return len(children)

    def delete(self, ids):
        self.calls.append(("delete", list(ids)))
        for child_id in ids:
            self.children.pop(child_id, None)
        return len(ids)

    def count(self):
        return len(self.children)


class FakeSQLiteSnapshot:
    def __init__(self):
        self.records = {}
        self.calls = []

    def sync(self, records, delete_ids, *, full_rebuild=False):
        self.calls.append(
            (
                "full" if full_rebuild else "incremental",
                [record.jd_id for record in records],
                list(delete_ids),
            )
        )
        if full_rebuild:
            self.records = {}
        for jd_id in delete_ids:
            self.records.pop(jd_id, None)
        self.records.update({record.jd_id: record for record in records})
        return len(self.records)

    def count(self):
        return len(self.records)


def _child(parent_id: str, child_type: str, content: str, digest: str):
    return JDChildDocument(
        child_id=f"{parent_id}:{child_type}",
        parent_id=parent_id,
        child_type=child_type,
        content=content,
        index_sha256=digest * 64,
        metadata={
            "parent_id": parent_id,
            "category": parent_id.split(":", 1)[0],
            "source": f"corpus/JD/{parent_id}/example.md",
            "title": "示例职位",
            "company": "示例公司",
            "relevance": "直接相关",
            "education": "本科及以上",
            "province": "湖北省",
            "salary_min_k": 10.0,
            "salary_max_k": 20.0,
        },
    )


def _parent(
    jd_id: str = "agent_dev:abc123def456",
    *,
    parent_hash: str = "a",
    row_hash: str = "b",
    jd_text_hash: str = "c",
    info_hash: str = "d",
):
    category, fingerprint = jd_id.split(":", 1)
    return JDParentDocument(
        jd_id=jd_id,
        fingerprint=fingerprint,
        category=category,
        source_path=f"corpus/JD/{category}/jobs/example.md",
        source_url="https://example.com/jobs/1",
        title="示例职位",
        company="示例公司",
        salary_raw="10k-20k",
        salary_min_k=10.0,
        salary_max_k=20.0,
        education="本科及以上",
        recruitment_count="1人",
        major="不限",
        region="湖北省武汉市",
        province="湖北省",
        source_updated_at="08-05",
        industry="软件",
        company_type="民营企业",
        company_size="100-499人",
        relevance="直接相关",
        relevance_score=60,
        function_category="Agent/AI 开发",
        keywords=("Python", "Agent"),
        duplicate_count=1,
        row_sha256=row_hash * 64,
        parent_sha256=parent_hash * 64,
        full_markdown="# 示例职位",
        children=(
            _child(jd_id, "jd_text", "职位原文", jd_text_hash),
            _child(jd_id, "job_info", "职位信息", info_hash),
        ),
    )


def _build(tmp_path, parents, repository, sqlite, embedding, **kwargs):
    return build_jd_index(
        parents=parents,
        repository=repository,
        embedding_client=embedding,
        embedding_model="fake-model",
        manifest_path=tmp_path / "index_manifest_jd.json",
        sync_sqlite=sqlite.sync,
        count_sqlite=sqlite.count,
        **kwargs,
    )


def test_first_build_indexes_all_children_and_writes_both_stores(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    embedding = FakeEmbedding()

    result = _build(tmp_path, [_parent()], repository, sqlite, embedding)

    assert result.mode == "full"
    assert result.parent_count == 1
    assert result.child_count == 2
    assert embedding.calls == [["职位原文", "职位信息"]]
    assert repository.calls == [
        (
            "rebuild",
            [
                "agent_dev:abc123def456:jd_text",
                "agent_dev:abc123def456:job_info",
            ],
        )
    ]
    assert sqlite.calls[0][0] == "full"
    assert (tmp_path / "index_manifest_jd.json").exists()


def test_unchanged_build_skips_embedding_and_mutations(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    first_embedding = FakeEmbedding()
    parent = _parent()
    _build(tmp_path, [parent], repository, sqlite, first_embedding)
    repository.calls.clear()
    sqlite.calls.clear()
    embedding = FakeEmbedding()

    result = _build(tmp_path, [parent], repository, sqlite, embedding)

    assert result.mode == "unchanged"
    assert embedding.calls == []
    assert repository.calls == []
    assert sqlite.calls == []


def test_analysis_only_change_updates_sqlite_without_embedding(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    original = _parent()
    _build(tmp_path, [original], repository, sqlite, FakeEmbedding())
    repository.calls.clear()
    sqlite.calls.clear()
    changed = replace(
        original,
        parent_sha256="e" * 64,
        full_markdown="# 示例职位\n\n新分析",
    )
    embedding = FakeEmbedding()

    result = _build(tmp_path, [changed], repository, sqlite, embedding)

    assert result.mode == "incremental"
    assert result.updated_parent_count == 1
    assert result.updated_child_count == 0
    assert embedding.calls == []
    assert repository.calls == []
    assert sqlite.calls == [("incremental", [changed.jd_id], [])]


def test_changed_child_only_embeds_and_upserts_that_child(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    original = _parent()
    _build(tmp_path, [original], repository, sqlite, FakeEmbedding())
    repository.calls.clear()
    sqlite.calls.clear()
    changed_child = replace(
        original.children[0],
        content="更新后的职位原文",
        index_sha256="f" * 64,
    )
    changed = replace(original, children=(changed_child, original.children[1]))
    embedding = FakeEmbedding()

    result = _build(tmp_path, [changed], repository, sqlite, embedding)

    assert result.updated_child_count == 1
    assert embedding.calls == [["更新后的职位原文"]]
    assert repository.calls == [
        ("upsert", ["agent_dev:abc123def456:jd_text"])
    ]


def test_removed_parent_deletes_sqlite_row_and_both_children(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    first, second = _parent(), _parent("marketing:def456abc123")
    _build(tmp_path, [first, second], repository, sqlite, FakeEmbedding())
    repository.calls.clear()
    sqlite.calls.clear()

    result = _build(tmp_path, [first], repository, sqlite, FakeEmbedding())

    assert result.deleted_parent_count == 1
    assert result.deleted_child_count == 2
    assert sqlite.calls == [("incremental", [], [second.jd_id])]
    assert repository.calls == [
        (
            "delete",
            [
                "marketing:def456abc123:jd_text",
                "marketing:def456abc123:job_info",
            ],
        )
    ]


def test_dry_run_reports_diff_without_embedding_or_writes(tmp_path):
    repository = FakeVectorRepository()
    sqlite = FakeSQLiteSnapshot()
    embedding = FakeEmbedding()

    result = _build(
        tmp_path,
        [_parent()],
        repository,
        sqlite,
        embedding,
        dry_run=True,
    )

    assert result.mode == "dry-run-full"
    assert result.updated_parent_count == 1
    assert result.updated_child_count == 2
    assert embedding.calls == []
    assert repository.calls == []
    assert sqlite.calls == []
    assert not (tmp_path / "index_manifest_jd.json").exists()
