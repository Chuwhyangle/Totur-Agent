"""Fail-closed readiness checks for the committed public JD snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.services.jd_index_manifest import JDIndexManifest, load_jd_manifest


class JDIndexNotReadyError(RuntimeError):
    """The SQLite, Chroma, and manifest snapshot is not committed."""


def load_ready_jd_manifest(
    manifest_path: Path,
    *,
    collection_name: str,
    vector_count: int,
    sqlite_table: str,
    vector_snapshot: Mapping[str, str],
    sqlite_snapshot: Mapping[str, tuple[str, str]],
    sqlite_count: int,
) -> JDIndexManifest:
    """Load a manifest only when both stores match the committed snapshot."""

    try:
        manifest = load_jd_manifest(manifest_path)
    except ValueError as exc:
        raise JDIndexNotReadyError(str(exc)) from exc
    if manifest.collection_name != collection_name:
        raise JDIndexNotReadyError("JD collection does not match manifest")
    if manifest.sqlite_table != sqlite_table:
        raise JDIndexNotReadyError("JD SQLite table does not match manifest")
    if vector_count != manifest.child_count:
        raise JDIndexNotReadyError("JD vector count does not match manifest")
    if sqlite_count != manifest.parent_count:
        raise JDIndexNotReadyError("JD SQLite count does not match manifest")
    expected_vector_snapshot = {
        child.child_id: child.index_sha256
        for parent in manifest.parents
        for child in parent.children
    }
    if dict(vector_snapshot) != expected_vector_snapshot:
        raise JDIndexNotReadyError("JD Chroma snapshot does not match manifest")
    expected_sqlite_snapshot = {
        parent.jd_id: (parent.row_sha256, parent.parent_sha256)
        for parent in manifest.parents
    }
    if dict(sqlite_snapshot) != expected_sqlite_snapshot:
        raise JDIndexNotReadyError("JD SQLite snapshot does not match manifest")
    return manifest
