import pytest

from app.services.jd_index_manifest import (
    JDChildManifest,
    JDIndexManifest,
    JDParentManifest,
    write_jd_manifest,
)
from app.services.jd_index_state import JDIndexNotReadyError, load_ready_jd_manifest


def _manifest():
    parent = JDParentManifest(
        jd_id="agent_dev:abc123",
        fingerprint="abc123",
        category="agent_dev",
        source_path="corpus/JD/agent_dev/jobs/example.md",
        parent_sha256="a" * 64,
        row_sha256="b" * 64,
        children=(
            JDChildManifest(
                child_id="agent_dev:abc123:jd_text",
                child_type="jd_text",
                index_sha256="c" * 64,
            ),
            JDChildManifest(
                child_id="agent_dev:abc123:job_info",
                child_type="job_info",
                index_sha256="d" * 64,
            ),
        ),
    )
    return JDIndexManifest.create(
        collection_name="job_descriptions",
        sqlite_table="public_job_descriptions",
        built_at="2026-08-05T10:00:00+00:00",
        embedding_model="fake-model",
        embedding_dimensions=3,
        parents=[parent],
    )


def test_ready_check_rejects_same_counts_with_wrong_snapshot_content(tmp_path):
    manifest = _manifest()
    path = tmp_path / "index_manifest_jd.json"
    write_jd_manifest(path, manifest)

    with pytest.raises(JDIndexNotReadyError, match="Chroma snapshot"):
        load_ready_jd_manifest(
            path,
            collection_name="job_descriptions",
            vector_count=2,
            vector_snapshot={
                "agent_dev:abc123:jd_text": "e" * 64,
                "agent_dev:abc123:job_info": "d" * 64,
            },
            sqlite_table="public_job_descriptions",
            sqlite_count=1,
            sqlite_snapshot={"agent_dev:abc123": ("b" * 64, "a" * 64)},
        )


def test_ready_check_accepts_matching_parent_and_child_snapshots(tmp_path):
    manifest = _manifest()
    path = tmp_path / "index_manifest_jd.json"
    write_jd_manifest(path, manifest)

    loaded = load_ready_jd_manifest(
        path,
        collection_name="job_descriptions",
        vector_count=2,
        vector_snapshot={
            "agent_dev:abc123:jd_text": "c" * 64,
            "agent_dev:abc123:job_info": "d" * 64,
        },
        sqlite_table="public_job_descriptions",
        sqlite_count=1,
        sqlite_snapshot={"agent_dev:abc123": ("b" * 64, "a" * 64)},
    )

    assert loaded == manifest
