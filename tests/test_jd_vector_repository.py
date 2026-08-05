import chromadb

from app.repositories.jd_vector_repository import JDVectorRepository
from app.services.jd_corpus import JDChildDocument


def _child(child_type: str, content: str, *, category: str = "agent_dev"):
    parent_id = "agent_dev:abc123def456"
    metadata = {
        "parent_id": parent_id,
        "category": category,
        "source": "corpus/JD/agent_dev/jobs/example.md",
        "title": "Agent工程师",
        "company": "示例公司",
        "relevance": "直接相关",
        "education": "本科及以上",
        "province": "湖北省",
        "salary_min_k": 16.0,
        "salary_max_k": 20.0,
    }
    return JDChildDocument(
        child_id=f"{parent_id}:{child_type}",
        parent_id=parent_id,
        child_type=child_type,
        content=content,
        index_sha256="a" * 64,
        metadata=metadata,
    )


def test_rebuild_upsert_delete_and_metadata_filter():
    repository = JDVectorRepository(client=chromadb.EphemeralClient())
    children = [
        _child("jd_text", "负责 Python Agent 和 RAG 开发"),
        _child("job_info", "本科及以上，湖北省，16k-20k"),
    ]
    embeddings = [[1.0, 0.0], [0.9, 0.1]]

    assert repository.rebuild(children, embeddings) == 2
    assert repository.count() == 2
    assert repository.snapshot_hashes() == {
        child.child_id: child.index_sha256 for child in children
    }
    assert repository.upsert([children[0]], [[0.8, 0.2]]) == 1
    assert repository.count() == 2

    hits = repository.search(
        query_embedding=[1.0, 0.0],
        top_k=5,
        where={"education": "本科及以上"},
    )
    assert len(hits) == 2
    assert all(hit.source.endswith("example.md") for hit in hits)

    assert repository.delete([children[1].child_id]) == 1
    assert repository.count() == 1


def test_upsert_creates_missing_collection_and_list_entries_applies_filter():
    repository = JDVectorRepository(client=chromadb.EphemeralClient())
    child = _child("jd_text", "Python Agent", category="agent_dev")

    assert repository.upsert([child], [[1.0, 0.0]]) == 1
    entries = repository.list_entries(where={"category": "agent_dev"})
    assert [entry.chunk_id for entry in entries] == [child.child_id]
    assert repository.list_entries(where={"category": "marketing"}) == []
