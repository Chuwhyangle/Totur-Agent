import hashlib
from types import SimpleNamespace

from app.db.models import PublicJDRecord
from app.repositories.knowledge_repository import KnowledgeHit
from app.services.agent.tools import search_job_descriptions as tool_module
from app.services.jd_index_manifest import (
    JDChildManifest,
    JDIndexManifest,
    JDParentManifest,
    write_jd_manifest,
)


class FakeRepository:
    collection_name = "job_descriptions"

    def __init__(self, count=6):
        self._count = count

    def count(self):
        return self._count

    def snapshot_hashes(self):
        parent_ids = (
            "agent_dev:samefinger01",
            "marketing:samefinger01",
            "agent_dev:unique000002",
        )
        return {
            f"{parent_id}:{child_type}": digest
            for parent_id in parent_ids
            for child_type, digest in (
                ("jd_text", "c" * 64),
                ("job_info", "d" * 64),
            )
        }


class FakeEmbedding:
    def __init__(self, model="fake-model"):
        self.calls = []
        self.config = SimpleNamespace(model=model)

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [[1.0, 0.0, 0.0]]


def _record(
    jd_id,
    fingerprint,
    category,
    source_path,
    title,
    *,
    parent_sha256="b" * 64,
):
    return PublicJDRecord(
        jd_id=jd_id,
        fingerprint=fingerprint,
        category=category,
        source_path=source_path,
        source_url="https://example.com/jobs/1",
        title=title,
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
        row_sha256="a" * 64,
        parent_sha256=parent_sha256,
    )


def _write_ready_snapshot(tmp_path):
    specs = [
        (
            "agent_dev:samefinger01",
            "samefinger01",
            "agent_dev",
            "corpus/JD/agent_dev/jobs/one.md",
            "Agent职位完整内容",
            "Agent工程师",
        ),
        (
            "marketing:samefinger01",
            "samefinger01",
            "marketing",
            "corpus/JD/marketing/jobs/duplicate.md",
            "重复职位完整内容",
            "AI内容运营",
        ),
        (
            "agent_dev:unique000002",
            "unique000002",
            "agent_dev",
            "corpus/JD/agent_dev/jobs/two.md",
            "第二份 Agent 职位完整内容",
            "AI应用开发",
        ),
    ]
    parents = []
    records = []
    for jd_id, fingerprint, category, source, content, title in specs:
        path = tmp_path / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        parents.append(
            JDParentManifest(
                jd_id=jd_id,
                fingerprint=fingerprint,
                category=category,
                source_path=source,
                parent_sha256=digest,
                row_sha256="a" * 64,
                children=(
                    JDChildManifest(
                        child_id=f"{jd_id}:jd_text",
                        child_type="jd_text",
                        index_sha256="c" * 64,
                    ),
                    JDChildManifest(
                        child_id=f"{jd_id}:job_info",
                        child_type="job_info",
                        index_sha256="d" * 64,
                    ),
                ),
            )
        )
        records.append(
            _record(
                jd_id,
                fingerprint,
                category,
                source,
                title,
                parent_sha256=digest,
            )
        )
    manifest = JDIndexManifest.create(
        collection_name="job_descriptions",
        sqlite_table="public_job_descriptions",
        built_at="2026-08-05T10:00:00+00:00",
        embedding_model="fake-model",
        embedding_dimensions=3,
        parents=parents,
    )
    manifest_path = tmp_path / "index_manifest_jd.json"
    write_jd_manifest(manifest_path, manifest)
    return manifest_path, records


def test_search_groups_children_and_deduplicates_cross_category_fingerprint(
    monkeypatch, tmp_path
):
    manifest_path, records = _write_ready_snapshot(tmp_path)
    captured = {}

    def fake_hybrid_search(**kwargs):
        captured["where"] = kwargs["repository"].where
        return [
            KnowledgeHit(
                "Agent职责命中",
                records[0].source_path,
                "jd_text",
                0.91,
            ),
            KnowledgeHit(
                "Agent信息命中",
                records[0].source_path,
                "job_info",
                0.84,
            ),
            KnowledgeHit(
                "重复方向命中",
                records[1].source_path,
                "jd_text",
                0.88,
            ),
            KnowledgeHit(
                "营销职责命中",
                records[2].source_path,
                "jd_text",
                0.75,
            ),
        ]

    monkeypatch.setattr(tool_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(tool_module, "_get_repository", lambda: FakeRepository())
    embedding = FakeEmbedding()
    monkeypatch.setattr(tool_module, "_get_embedding_client", lambda: embedding)

    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: records)
    monkeypatch.setattr(tool_module, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", False)

    result = tool_module.search_job_descriptions(
        "Python Agent",
        limit=3,
        direction="agent_dev",
        education="本科及以上",
        province="湖北省",
        salary_floor_k=10,
        salary_ceiling_k=25,
    )

    assert result["ok"] is True
    assert result["count"] == 2
    assert [item["fingerprint"] for item in result["results"]] == [
        "samefinger01",
        "unique000002",
    ]
    assert result["results"][0]["content"] == "Agent职位完整内容"
    assert result["results"][0]["categories"] == ["agent_dev", "marketing"]
    assert result["results"][0]["matched_child_type"] == "jd_text"
    assert embedding.calls == [["Python Agent"]]
    assert captured["where"] == {
        "$and": [
            {"category": "agent_dev"},
            {"education": "本科及以上"},
            {"province": "湖北省"},
            {"salary_min_k": {"$gte": 10.0}},
            {"salary_max_k": {"$lte": 25.0}},
        ]
    }


def test_search_rejects_parent_hash_mismatch(monkeypatch, tmp_path):
    manifest_path, records = _write_ready_snapshot(tmp_path)
    source_path = tmp_path / records[0].source_path
    source_path.write_text("文件已经变化", encoding="utf-8")
    monkeypatch.setattr(tool_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(tool_module, "_get_repository", lambda: FakeRepository())
    monkeypatch.setattr(tool_module, "_get_embedding_client", lambda: FakeEmbedding())

    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: records)
    monkeypatch.setattr(
        tool_module,
        "hybrid_search",
        lambda **kwargs: [
            KnowledgeHit("命中", records[0].source_path, "jd_text", 0.9)
        ],
    )
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", False)

    result = tool_module.search_job_descriptions("Agent")

    assert result["ok"] is False
    assert result["error"] == "jd_index_stale"


def test_search_reports_not_ready_without_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(tool_module, "_get_repository", lambda: FakeRepository())
    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: [])


    result = tool_module.search_job_descriptions("Agent")

    assert result["ok"] is False
    assert result["error"] == "jd_index_not_ready"


def test_search_uses_vector_only_when_hybrid_is_disabled(monkeypatch, tmp_path):
    manifest_path, records = _write_ready_snapshot(tmp_path)
    repository = FakeRepository()
    repository.search = lambda query_embedding, top_k, where=None: [
        KnowledgeHit("命中", records[0].source_path, "jd_text", 0.9)
    ]
    monkeypatch.setattr(tool_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(tool_module, "_get_repository", lambda: repository)
    monkeypatch.setattr(tool_module, "_get_embedding_client", lambda: FakeEmbedding())

    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: records)
    monkeypatch.setattr(tool_module, "ENABLE_HYBRID_RETRIEVAL", False, raising=False)
    monkeypatch.setattr(
        tool_module,
        "hybrid_search",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("hybrid must be off")),
    )
    monkeypatch.setattr(tool_module, "ENABLE_RERANKING", False)

    result = tool_module.search_job_descriptions("Agent")

    assert result["ok"] is True
    assert result["count"] == 1


def test_search_rejects_embedding_model_mismatch_before_embedding(monkeypatch, tmp_path):
    manifest_path, records = _write_ready_snapshot(tmp_path)
    embedding = FakeEmbedding(model="other-model")
    monkeypatch.setattr(tool_module, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(tool_module, "_get_repository", lambda: FakeRepository())
    monkeypatch.setattr(tool_module, "_get_embedding_client", lambda: embedding)

    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: records)

    result = tool_module.search_job_descriptions("Agent")

    assert result["ok"] is False
    assert result["error"] == "jd_index_not_ready"
    assert embedding.calls == []
