"""Versioned commit manifest for the public JD parent-child index."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


SHA256_RE = re.compile(r"[0-9a-f]{64}")
JD_MANIFEST_SCHEMA_VERSION = 1
JD_CHILD_SCHEMA_VERSION = 1


@dataclass(frozen=True, order=True)
class JDChildManifest:
    child_id: str
    child_type: str
    index_sha256: str


@dataclass(frozen=True, order=True)
class JDParentManifest:
    jd_id: str
    fingerprint: str
    category: str
    source_path: str
    parent_sha256: str
    row_sha256: str
    children: tuple[JDChildManifest, ...]


@dataclass(frozen=True)
class JDIndexManifest:
    schema_version: int
    child_schema_version: int
    fingerprint: str
    collection_name: str
    sqlite_table: str
    built_at: str
    embedding_model: str
    embedding_dimensions: int
    parents: tuple[JDParentManifest, ...]

    @property
    def parent_count(self) -> int:
        return len(self.parents)

    @property
    def child_count(self) -> int:
        return sum(len(parent.children) for parent in self.parents)

    @classmethod
    def create(
        cls,
        *,
        collection_name: str,
        sqlite_table: str,
        built_at: str,
        embedding_model: str,
        embedding_dimensions: int,
        parents: Iterable[JDParentManifest],
    ) -> "JDIndexManifest":
        normalized = tuple(sorted(parents))
        candidate = cls(
            schema_version=JD_MANIFEST_SCHEMA_VERSION,
            child_schema_version=JD_CHILD_SCHEMA_VERSION,
            fingerprint="",
            collection_name=collection_name,
            sqlite_table=sqlite_table,
            built_at=built_at,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            parents=normalized,
        )
        candidate._validate()
        result = replace(candidate, fingerprint=candidate.compute_fingerprint())
        result._validate(require_fingerprint=True)
        return result

    def stable_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "child_schema_version": self.child_schema_version,
            "collection_name": self.collection_name,
            "sqlite_table": self.sqlite_table,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "parents": [
                {
                    "jd_id": parent.jd_id,
                    "fingerprint": parent.fingerprint,
                    "category": parent.category,
                    "source_path": parent.source_path,
                    "parent_sha256": parent.parent_sha256,
                    "row_sha256": parent.row_sha256,
                    "children": [
                        {
                            "child_id": child.child_id,
                            "child_type": child.child_type,
                            "index_sha256": child.index_sha256,
                        }
                        for child in parent.children
                    ],
                }
                for parent in self.parents
            ],
        }

    def compute_fingerprint(self) -> str:
        canonical = json.dumps(
            self.stable_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def to_dict(self) -> dict[str, Any]:
        self._validate(require_fingerprint=True)
        payload = self.stable_payload()
        payload.update(
            {
                "fingerprint": self.fingerprint,
                "built_at": self.built_at,
                "parent_count": self.parent_count,
                "child_count": self.child_count,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, raw: Any) -> "JDIndexManifest":
        if not isinstance(raw, dict):
            raise ValueError("JD manifest root must be an object")
        try:
            parents = tuple(
                JDParentManifest(
                    jd_id=item["jd_id"],
                    fingerprint=item["fingerprint"],
                    category=item["category"],
                    source_path=item["source_path"],
                    parent_sha256=item["parent_sha256"],
                    row_sha256=item["row_sha256"],
                    children=tuple(
                        JDChildManifest(
                            child_id=child["child_id"],
                            child_type=child["child_type"],
                            index_sha256=child["index_sha256"],
                        )
                        for child in item["children"]
                    ),
                )
                for item in raw["parents"]
            )
            manifest = cls(
                schema_version=raw["schema_version"],
                child_schema_version=raw["child_schema_version"],
                fingerprint=raw["fingerprint"],
                collection_name=raw["collection_name"],
                sqlite_table=raw["sqlite_table"],
                built_at=raw["built_at"],
                embedding_model=raw["embedding_model"],
                embedding_dimensions=raw["embedding_dimensions"],
                parents=parents,
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid JD manifest shape") from exc
        if raw.get("parent_count") != manifest.parent_count:
            raise ValueError("JD manifest parent_count does not match")
        if raw.get("child_count") != manifest.child_count:
            raise ValueError("JD manifest child_count does not match")
        manifest._validate(require_fingerprint=True)
        return manifest

    def _validate(self, *, require_fingerprint: bool = False) -> None:
        if self.schema_version != JD_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported JD manifest schema_version")
        if self.child_schema_version != JD_CHILD_SCHEMA_VERSION:
            raise ValueError("unsupported JD child_schema_version")
        if not self.collection_name.strip() or not self.sqlite_table.strip():
            raise ValueError("JD manifest storage names must be non-empty")
        if not self.embedding_model.strip() or self.embedding_dimensions <= 0:
            raise ValueError("JD manifest embedding signature is invalid")
        if not self.parents:
            raise ValueError("JD manifest must contain parents")
        parent_ids = [parent.jd_id for parent in self.parents]
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("duplicate parent id in JD manifest")
        for parent in self.parents:
            _validate_parent(parent)
        if require_fingerprint and self.fingerprint != self.compute_fingerprint():
            raise ValueError("JD manifest fingerprint does not match")


def write_jd_manifest(path: Path, manifest: JDIndexManifest) -> None:
    """Atomically write a validated UTF-8 manifest."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp")
    temporary.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(destination)


def load_jd_manifest(path: Path) -> JDIndexManifest:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"cannot read JD manifest: {path}") from exc
    return JDIndexManifest.from_dict(raw)


def _validate_parent(parent: JDParentManifest) -> None:
    if not parent.jd_id or not parent.fingerprint or not parent.category:
        raise ValueError("JD manifest parent identity is invalid")
    source = PurePosixPath(parent.source_path)
    if source.is_absolute() or ".." in source.parts or "\\" in parent.source_path:
        raise ValueError("JD manifest source_path must be relative POSIX")
    for digest in (parent.parent_sha256, parent.row_sha256):
        if not SHA256_RE.fullmatch(digest):
            raise ValueError("JD manifest parent hash is invalid")
    if tuple(sorted(parent.children)) != parent.children:
        raise ValueError("JD manifest children must be sorted")
    child_ids = [child.child_id for child in parent.children]
    if len(child_ids) != len(set(child_ids)):
        raise ValueError("duplicate child id in JD manifest")
    if {child.child_type for child in parent.children} != {"jd_text", "job_info"}:
        raise ValueError("JD manifest parent must have both child types")
    for child in parent.children:
        if not child.child_id.startswith(f"{parent.jd_id}:"):
            raise ValueError("JD manifest child parent does not match")
        if not SHA256_RE.fullmatch(child.index_sha256):
            raise ValueError("JD manifest child hash is invalid")
