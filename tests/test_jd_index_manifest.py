from app.services.jd_index_manifest import (
    JDChildManifest,
    JDIndexManifest,
    JDParentManifest,
    load_jd_manifest,
    write_jd_manifest,
)


def _parent(jd_id: str = "agent_dev:abc123def456") -> JDParentManifest:
    return JDParentManifest(
        jd_id=jd_id,
        fingerprint="abc123def456",
        category="agent_dev",
        source_path="corpus/JD/agent_dev/jobs/example.md",
        parent_sha256="a" * 64,
        row_sha256="b" * 64,
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


def test_manifest_round_trip_and_fingerprint_ignore_build_time(tmp_path):
    first = JDIndexManifest.create(
        collection_name="job_descriptions",
        sqlite_table="public_job_descriptions",
        built_at="2026-08-05T10:00:00+00:00",
        embedding_model="fake-model",
        embedding_dimensions=3,
        parents=[_parent()],
    )
    second = JDIndexManifest.create(
        collection_name="job_descriptions",
        sqlite_table="public_job_descriptions",
        built_at="2026-08-05T11:00:00+00:00",
        embedding_model="fake-model",
        embedding_dimensions=3,
        parents=[_parent()],
    )
    path = tmp_path / "index_manifest_jd.json"

    write_jd_manifest(path, first)

    assert first.parent_count == 1
    assert first.child_count == 2
    assert first.fingerprint == second.fingerprint
    assert load_jd_manifest(path) == first


def test_manifest_rejects_duplicate_parent_ids():
    try:
        JDIndexManifest.create(
            collection_name="job_descriptions",
            sqlite_table="public_job_descriptions",
            built_at="2026-08-05T10:00:00+00:00",
            embedding_model="fake-model",
            embedding_dimensions=3,
            parents=[_parent(), _parent()],
        )
    except ValueError as exc:
        assert "duplicate parent" in str(exc)
    else:
        raise AssertionError("duplicate parent ids must be rejected")
