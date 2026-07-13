"""Stable, validated manifests for persisted RAG indexes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ManifestError(ValueError):
    """Raised when an index Manifest cannot be validated or persisted."""


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of the original bytes."""

    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True, order=True)
class CorpusFileManifest:
    """Stable identity and chunk total for one corpus file."""

    path: str
    content_sha256: str
    chunk_count: int


@dataclass(frozen=True)
class IndexManifest:
    """Versioned description of all inputs used to build a RAG index."""

    schema_version: int
    fingerprint: str
    collection_name: str
    built_at: str
    embedding_model: str
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int
    corpus_root: str
    files: tuple[CorpusFileManifest, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def chunk_count(self) -> int:
        return sum(item.chunk_count for item in self.files)

    @classmethod
    def create(
        cls,
        schema_version: int,
        collection_name: str,
        built_at: str,
        embedding_model: str,
        embedding_dimensions: int,
        chunk_size: int,
        chunk_overlap: int,
        corpus_root: str,
        files: Iterable[CorpusFileManifest],
    ) -> IndexManifest:
        """Create a validated manifest, normalizing corpus files by order."""

        try:
            normalized_files = tuple(files)
        except (TypeError, ValueError) as exc:
            raise ManifestError("corpus files must be an iterable") from exc

        for item in normalized_files:
            cls._validate_file(item)

        try:
            normalized_files = tuple(sorted(normalized_files))
        except TypeError as exc:
            raise ManifestError("corpus files must be orderable") from exc

        candidate = cls(
            schema_version=schema_version,
            fingerprint="",
            collection_name=collection_name,
            built_at=built_at,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            corpus_root=corpus_root,
            files=normalized_files,
        )
        candidate._validate_fields()
        result = replace(candidate, fingerprint=candidate.compute_fingerprint())
        result.validate()
        return result

    def stable_payload(self) -> dict[str, Any]:
        """Return only the stable index inputs included in the fingerprint."""

        return {
            "schema_version": self.schema_version,
            "collection_name": self.collection_name,
            "embedding": {
                "model": self.embedding_model,
                "dimensions": self.embedding_dimensions,
            },
            "chunking": {
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            },
            "corpus": {
                "file_count": self.file_count,
                "chunk_count": self.chunk_count,
                "files": [
                    {
                        "path": item.path,
                        "content_sha256": item.content_sha256,
                        "chunk_count": item.chunk_count,
                    }
                    for item in self.files
                ],
            },
        }

    def compute_fingerprint(self) -> str:
        """Compute the canonical SHA-256 identity of stable index inputs."""

        try:
            canonical = json.dumps(
                self.stable_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ManifestError("cannot compute Manifest fingerprint") from exc
        return f"sha256:{sha256_bytes(canonical)}"

    def validate(self) -> None:
        """Validate schema constraints and the stored fingerprint."""

        self._validate_fields()
        expected = self.compute_fingerprint()
        if self.fingerprint != expected:
            raise ManifestError("Manifest fingerprint does not match its stable payload")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this manifest to the schema-version-one JSON shape."""

        self.validate()
        return {
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "collection_name": self.collection_name,
            "built_at": self.built_at,
            "embedding": {
                "model": self.embedding_model,
                "dimensions": self.embedding_dimensions,
            },
            "chunking": {
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            },
            "corpus": {
                "root": self.corpus_root,
                "file_count": self.file_count,
                "chunk_count": self.chunk_count,
                "files": [
                    {
                        "path": item.path,
                        "content_sha256": item.content_sha256,
                        "chunk_count": item.chunk_count,
                    }
                    for item in self.files
                ],
            },
        }

    @classmethod
    def from_dict(cls, raw: Any) -> IndexManifest:
        """Parse and validate a manifest from its JSON-compatible mapping."""

        try:
            cls._require_keys(
                raw,
                {
                    "schema_version",
                    "fingerprint",
                    "collection_name",
                    "built_at",
                    "embedding",
                    "chunking",
                    "corpus",
                },
                "root",
            )
            embedding = raw["embedding"]
            chunking = raw["chunking"]
            corpus = raw["corpus"]
            cls._require_keys(embedding, {"model", "dimensions"}, "embedding")
            cls._require_keys(
                chunking,
                {"chunk_size", "chunk_overlap"},
                "chunking",
            )
            cls._require_keys(
                corpus,
                {"root", "file_count", "chunk_count", "files"},
                "corpus",
            )

            raw_files = corpus["files"]
            if not isinstance(raw_files, list):
                raise ManifestError("invalid Manifest shape: corpus.files must be an array")

            files: list[CorpusFileManifest] = []
            for index, raw_file in enumerate(raw_files):
                cls._require_keys(
                    raw_file,
                    {"path", "content_sha256", "chunk_count"},
                    f"corpus.files[{index}]",
                )
                files.append(
                    CorpusFileManifest(
                        path=raw_file["path"],
                        content_sha256=raw_file["content_sha256"],
                        chunk_count=raw_file["chunk_count"],
                    )
                )

            manifest = cls(
                schema_version=raw["schema_version"],
                fingerprint=raw["fingerprint"],
                collection_name=raw["collection_name"],
                built_at=raw["built_at"],
                embedding_model=embedding["model"],
                embedding_dimensions=embedding["dimensions"],
                chunk_size=chunking["chunk_size"],
                chunk_overlap=chunking["chunk_overlap"],
                corpus_root=corpus["root"],
                files=tuple(files),
            )

            declared_file_count = corpus["file_count"]
            if not _is_int(declared_file_count):
                raise ManifestError("invalid Manifest shape: file_count must be an integer")
            if declared_file_count != manifest.file_count:
                raise ManifestError(
                    "declared file_count does not match the corpus files"
                )

            declared_chunk_count = corpus["chunk_count"]
            if not _is_int(declared_chunk_count):
                raise ManifestError("invalid Manifest shape: chunk_count must be an integer")
            if declared_chunk_count != manifest.chunk_count:
                raise ManifestError(
                    "declared chunk_count does not match the corpus files"
                )

            manifest.validate()
            return manifest
        except ManifestError:
            raise
        except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
            raise ManifestError("invalid Manifest shape") from exc

    def _validate_fields(self) -> None:
        if not _is_int(self.schema_version) or self.schema_version != 1:
            raise ManifestError("schema_version must be 1")
        if not _nonempty_string(self.collection_name):
            raise ManifestError("collection_name must be a non-empty string")
        if not isinstance(self.built_at, str):
            raise ManifestError("built_at must be a string")
        if not _nonempty_string(self.embedding_model):
            raise ManifestError("embedding model must be a non-empty string")
        if not _is_int(self.embedding_dimensions) or self.embedding_dimensions <= 0:
            raise ManifestError("embedding dimensions must be a positive integer")
        if not _is_int(self.chunk_size) or self.chunk_size <= 0:
            raise ManifestError("chunking requires a positive chunk_size")
        if (
            not _is_int(self.chunk_overlap)
            or self.chunk_overlap < 0
            or self.chunk_overlap >= self.chunk_size
        ):
            raise ManifestError(
                "chunking requires 0 <= chunk_overlap < chunk_size"
            )
        if not isinstance(self.corpus_root, str):
            raise ManifestError("corpus root must be a string")
        if not isinstance(self.files, tuple) or not self.files:
            raise ManifestError("corpus files must be a non-empty tuple")

        for item in self.files:
            self._validate_file(item)

        try:
            sorted_files = tuple(sorted(self.files))
        except TypeError as exc:
            raise ManifestError("corpus files must be sorted") from exc
        if self.files != sorted_files:
            raise ManifestError("corpus files must be sorted")

    @staticmethod
    def _validate_file(item: Any) -> None:
        if not isinstance(item, CorpusFileManifest):
            raise ManifestError("corpus files must contain CorpusFileManifest records")
        if not isinstance(item.path, str) or not item.path or "\\" in item.path:
            raise ManifestError("file path must be a relative POSIX corpus path")

        path = PurePosixPath(item.path)
        is_windows_absolute = (
            len(item.path) >= 2
            and item.path[0].isalpha()
            and item.path[1] == ":"
        )
        if (
            path.is_absolute()
            or is_windows_absolute
            or ".." in path.parts
            or path == PurePosixPath(".")
            or "\x00" in item.path
        ):
            raise ManifestError("file path must be a relative POSIX corpus path")
        if not isinstance(item.content_sha256, str) or not _SHA256_RE.fullmatch(
            item.content_sha256
        ):
            raise ManifestError("content_sha256 must be 64 lowercase hex characters")
        if not _is_int(item.chunk_count) or item.chunk_count < 0:
            raise ManifestError("file chunk_count must be a non-negative integer")

    @staticmethod
    def _require_keys(raw: Any, expected: set[str], location: str) -> None:
        if not isinstance(raw, dict):
            raise ManifestError(
                f"invalid Manifest shape: {location} must be an object"
            )
        if set(raw) != expected:
            raise ManifestError(
                f"invalid Manifest shape: {location} has unexpected fields"
            )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def write_manifest(path: str | Path, manifest: IndexManifest) -> None:
    """Validate and atomically replace a UTF-8 JSON manifest."""

    try:
        manifest.validate()
    except ManifestError:
        raise
    except (TypeError, AttributeError, ValueError) as exc:
        raise ManifestError("invalid Manifest value") from exc

    temporary: Path | None = None
    try:
        destination = Path(path)
        temporary = destination.with_name(f"{destination.name}.tmp")
        destination.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        temporary.write_text(
            f"{serialized}\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(destination)
    except ManifestError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise ManifestError(f"cannot write Manifest: {path}") from exc


def load_manifest(path: str | Path) -> IndexManifest:
    """Load a UTF-8 JSON manifest and validate its full contents."""

    try:
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise ManifestError(f"cannot read Manifest: {path}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be a JSON object")
    return IndexManifest.from_dict(raw)
