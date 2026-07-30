"""Build deterministic hierarchical chunks from the Agent interview HTML corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.agent_doc_chunker import (
    ChunkingConfig,
    ChunkingError,
    TokenizerLike,
    build_chunk_records,
    parse_agent_doc_html,
    validate_chunk_records,
)


DEFAULT_TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-8B"
DEFAULT_SOURCE_DIR = Path("corpus/Agent_doc")
DEFAULT_OUTPUT_DIR = Path("corpus/Agent_doc/processed")
JSONL_NAME = "agent_doc_chunks.jsonl"
MANIFEST_NAME = "agent_doc_manifest.json"


class AgentDocBuildError(RuntimeError):
    """Raised for clear, user-facing corpus build failures."""


class HuggingFaceTokenizerAdapter:
    """Expose exact counts and offsets from one fast Hugging Face tokenizer."""

    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=True))

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        encoded = self._tokenizer(
            text,
            add_special_tokens=True,
            return_offsets_mapping=True,
            truncation=False,
        )
        mapping = encoded["offset_mapping"]
        if mapping and isinstance(mapping[0], list):
            mapping = mapping[0]
        return tuple((int(start), int(end)) for start, end in mapping)


@dataclass(frozen=True)
class LoadedTokenizer:
    tokenizer: TokenizerLike
    model: str
    revision: str
    library: str
    library_version: str
    add_special_tokens: bool

    def manifest_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "revision": self.revision,
            "library": self.library,
            "library_version": self.library_version,
            "add_special_tokens": self.add_special_tokens,
        }


def _sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _local_tokenizer_revision(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise AgentDocBuildError(f"local tokenizer directory is empty: {path}")
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = item.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"local-sha256:{digest.hexdigest()}"


def resolve_tokenizer_revision(
    model: str,
    revision: str | None,
    tokenizer: Any,
) -> str:
    """Resolve the exact tokenizer snapshot identity used for this build."""

    init_kwargs = getattr(tokenizer, "init_kwargs", {}) or {}
    resolved = init_kwargs.get("_commit_hash") or getattr(
        tokenizer, "_commit_hash", None
    )
    if resolved:
        return str(resolved)

    model_path = Path(model)
    if model_path.is_dir():
        return _local_tokenizer_revision(model_path.resolve())

    try:
        from huggingface_hub import try_to_load_from_cache

        for filename in ("tokenizer_config.json", "tokenizer.json", "config.json"):
            cached = try_to_load_from_cache(
                model,
                filename,
                revision=revision or "main",
            )
            if not isinstance(cached, (str, os.PathLike)):
                continue
            parts = Path(cached).parts
            if "snapshots" not in parts:
                continue
            index = parts.index("snapshots")
            if index + 1 < len(parts):
                commit = parts[index + 1]
                if re.fullmatch(r"[0-9a-f]{40,64}", commit):
                    return commit
    except Exception as exc:
        raise AgentDocBuildError(
            f"cannot inspect tokenizer cache revision for {model!r}: {exc}"
        ) from exc

    raise AgentDocBuildError(f"cannot resolve tokenizer revision for {model!r}")

def load_tokenizer(model: str, revision: str | None = None) -> LoadedTokenizer:
    """Load the requested matching fast tokenizer without approximation fallback."""

    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            model,
            revision=revision,
            use_fast=True,
        )
    except Exception as exc:
        raise AgentDocBuildError(
            f"cannot load matching tokenizer {model!r}: {exc}"
        ) from exc
    if not getattr(tokenizer, "is_fast", False):
        raise AgentDocBuildError(
            f"tokenizer {model!r} is not fast; offset mapping is required"
        )

    resolved_revision = resolve_tokenizer_revision(model, revision, tokenizer)

    try:
        library_version = metadata.version("transformers")
    except metadata.PackageNotFoundError as exc:  # pragma: no cover - import already proves install
        raise AgentDocBuildError("transformers package metadata is unavailable") from exc
    return LoadedTokenizer(
        tokenizer=HuggingFaceTokenizerAdapter(tokenizer),
        model=model,
        revision=str(resolved_revision),
        library="transformers",
        library_version=library_version,
        add_special_tokens=True,
    )


def _project_path(value: str | Path, *, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise AgentDocBuildError(
            f"{label} must stay inside project root: {resolved}"
        ) from exc
    return resolved


def _relative_posix(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AgentDocBuildError(
            f"source path is outside project root: {path}"
        ) from exc


def _scan_html(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        raise AgentDocBuildError(f"source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise AgentDocBuildError(f"source path is not a directory: {source_dir}")
    files = sorted(
        (path for path in source_dir.rglob("*.html") if path.is_file()),
        key=lambda path: _relative_posix(path),
    )
    if not files:
        raise AgentDocBuildError(f"source directory contains no HTML files: {source_dir}")
    return files


def _read_unique_sources(paths: list[Path]) -> list[tuple[Path, bytes, str]]:
    seen: dict[str, Path] = {}
    sources: list[tuple[Path, bytes, str]] = []
    duplicates: list[tuple[Path, Path]] = []
    for path in paths:
        try:
            content = path.read_bytes()
            content.decode("utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            raise AgentDocBuildError(f"cannot decode HTML as UTF-8: {path}: {exc}") from exc
        digest = _sha256_bytes(content)
        if digest in seen:
            duplicates.append((seen[digest], path))
        else:
            seen[digest] = path
        sources.append((path, content, digest))
    if duplicates:
        pairs = "; ".join(
            f"{_relative_posix(first)} == {_relative_posix(second)}"
            for first, second in duplicates
        )
        raise AgentDocBuildError(f"duplicate HTML content detected: {pairs}")
    return sources


def _infer_course_title(paths: list[Path]) -> str | None:
    parents = [str(path.parent.resolve()) for path in paths]
    common_parent = Path(os.path.commonpath(parents))
    name = common_parent.name.strip()
    if not re.search(r"\d+\s*讲", name):
        return None
    cleaned = re.sub(r"[（(]\s*\d+\s*讲.*?[）)]\s*$", "", name).strip()
    return cleaned or None


def _parse_documents(
    sources: list[tuple[Path, bytes, str]],
) -> list[Any]:
    course_title = _infer_course_title([path for path, _, _ in sources])
    if course_title is None:
        for path, content, _ in sources:
            html = content.decode("utf-8")
            if "course-card" not in html:
                continue
            document = parse_agent_doc_html(
                html,
                source=_relative_posix(path),
                course_title=None,
            )
            if document.kind == "course_map":
                course_title = document.course_title
                break
    documents = []
    for path, content, _ in sources:
        try:
            document = parse_agent_doc_html(
                content.decode("utf-8"),
                source=_relative_posix(path),
                course_title=course_title,
            )
        except (ValueError, TypeError) as exc:
            raise AgentDocBuildError(f"cannot parse HTML {_relative_posix(path)}: {exc}") from exc
        if not document.units:
            raise AgentDocBuildError(
                f"HTML produced zero semantic units: {_relative_posix(path)}"
            )
        documents.append(document)
    return documents


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(record) + b"\n" for record in records)


def _manifest_fingerprint(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "fingerprint"}
    return _sha256_bytes(_canonical_json_bytes(stable))


def _build_manifest(
    *,
    source_dir: Path,
    sources: list[tuple[Path, bytes, str]],
    records: list[dict[str, Any]],
    loaded_tokenizer: LoadedTokenizer,
    config: ChunkingConfig,
    jsonl_bytes: bytes,
) -> dict[str, Any]:
    counts_by_source = Counter(record["source"] for record in records)
    counts_by_type = Counter(record["chunk_type"] for record in records)
    files = [
        {
            "source": _relative_posix(path),
            "content_sha256": digest,
            "chunk_count": counts_by_source[_relative_posix(path)],
        }
        for path, _, digest in sources
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "source_root": _relative_posix(source_dir),
        "source_file_count": len(sources),
        "chunk_count": len(records),
        "chunk_counts_by_type": {
            key: counts_by_type[key] for key in sorted(counts_by_type)
        },
        "tokenizer": loaded_tokenizer.manifest_dict(),
        "chunking": {
            "split_threshold_tokens": config.split_threshold_tokens,
            "target_min_tokens": config.target_min_tokens,
            "target_max_tokens": config.target_max_tokens,
            "fallback_overlap_tokens": config.fallback_overlap_tokens,
        },
        "files": files,
        "output_sha256": _sha256_bytes(jsonl_bytes),
    }
    manifest["fingerprint"] = _manifest_fingerprint(manifest)
    return manifest


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _validate_serialized_outputs(
    *,
    jsonl_bytes: bytes,
    manifest: dict[str, Any],
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> None:
    try:
        records = [
            json.loads(line)
            for line in jsonl_bytes.decode("utf-8").splitlines()
            if line
        ]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AgentDocBuildError(f"generated JSONL is invalid: {exc}") from exc
    validate_chunk_records(records, tokenizer, config)
    if manifest.get("chunk_count") != len(records):
        raise AgentDocBuildError("Manifest chunk count does not match JSONL")
    if manifest.get("output_sha256") != _sha256_bytes(jsonl_bytes):
        raise AgentDocBuildError("Manifest output SHA-256 does not match JSONL")
    if manifest.get("fingerprint") != _manifest_fingerprint(manifest):
        raise AgentDocBuildError("Manifest fingerprint is invalid")


def _write_temp(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def atomic_write_outputs(
    *,
    jsonl_path: Path,
    jsonl_bytes: bytes,
    manifest_path: Path,
    manifest_bytes: bytes,
) -> None:
    """Replace JSONL and Manifest as one rollback-protected output pair."""

    temp_jsonl: Path | None = None
    temp_manifest: Path | None = None
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    finals = (jsonl_path, manifest_path)
    try:
        temp_jsonl = _write_temp(jsonl_path, jsonl_bytes)
        temp_manifest = _write_temp(manifest_path, manifest_bytes)
        for final in finals:
            if final.exists():
                backup = final.with_name(f".{final.name}.{uuid.uuid4().hex}.bak")
                os.replace(final, backup)
                backups[final] = backup
        for temp, final in ((temp_jsonl, jsonl_path), (temp_manifest, manifest_path)):
            os.replace(temp, final)
            installed.append(final)
        temp_jsonl = None
        temp_manifest = None
    except Exception as exc:
        rollback_errors: list[str] = []
        for final in installed:
            try:
                final.unlink(missing_ok=True)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        for final, backup in backups.items():
            try:
                os.replace(backup, final)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        detail = f": {exc}"
        if rollback_errors:
            detail += f"; rollback errors: {'; '.join(rollback_errors)}"
        raise AgentDocBuildError(f"atomic output replacement failed{detail}") from exc
    finally:
        if temp_jsonl is not None:
            temp_jsonl.unlink(missing_ok=True)
        if temp_manifest is not None:
            temp_manifest.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    index = round((len(values) - 1) * fraction)
    return sorted(values)[index]


def _print_report(
    *,
    source_count: int,
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    token_counts = [record["embedding_token_count"] for record in records]
    character_counts = [len(record["content"]) for record in records]
    type_summary = ", ".join(
        f"{key}={value}"
        for key, value in manifest["chunk_counts_by_type"].items()
    )
    print(f"source_files={source_count}")
    print(f"chunks={len(records)} ({type_summary})")
    print(
        "embedding_tokens="
        f"min:{min(token_counts)} p50:{_percentile(token_counts, 0.50)} "
        f"p95:{_percentile(token_counts, 0.95)} max:{max(token_counts)}"
    )
    print(
        "content_characters="
        f"min:{min(character_counts)} p50:{_percentile(character_counts, 0.50)} "
        f"p95:{_percentile(character_counts, 0.95)} max:{max(character_counts)}"
    )
    print(f"output_sha256={manifest['output_sha256']}")
    print(f"fingerprint={manifest['fingerprint']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic hierarchical chunks from Agent interview HTML files."
    )
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tokenizer-model", default=None)
    parser.add_argument("--tokenizer-revision", default=None)
    parser.add_argument("--split-threshold-tokens", type=int, default=1024)
    parser.add_argument("--target-min-tokens", type=int, default=500)
    parser.add_argument("--target-max-tokens", type=int, default=700)
    parser.add_argument("--fallback-overlap-tokens", type=int, default=64)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process-style status code."""

    try:
        load_dotenv(PROJECT_ROOT / ".env")
        args = build_parser().parse_args(argv)
        source_dir = _project_path(args.source_dir, label="source directory")
        output_dir = _project_path(args.output_dir, label="output directory")
        tokenizer_model = (
            args.tokenizer_model
            or os.getenv("EMBEDDING_MODEL", "").strip()
            or DEFAULT_TOKENIZER_MODEL
        )
        config = ChunkingConfig(
            split_threshold_tokens=args.split_threshold_tokens,
            target_min_tokens=args.target_min_tokens,
            target_max_tokens=args.target_max_tokens,
            fallback_overlap_tokens=args.fallback_overlap_tokens,
        )
        paths = _scan_html(source_dir)
        sources = _read_unique_sources(paths)
        loaded = load_tokenizer(tokenizer_model, args.tokenizer_revision)
        documents = _parse_documents(sources)
        units = [unit for document in documents for unit in document.units]
        records = build_chunk_records(units, loaded.tokenizer, config)
        if not records:
            raise AgentDocBuildError("chunk build produced zero records")
        jsonl_bytes = _jsonl_bytes(records)
        manifest = _build_manifest(
            source_dir=source_dir,
            sources=sources,
            records=records,
            loaded_tokenizer=loaded,
            config=config,
            jsonl_bytes=jsonl_bytes,
        )
        _validate_serialized_outputs(
            jsonl_bytes=jsonl_bytes,
            manifest=manifest,
            tokenizer=loaded.tokenizer,
            config=config,
        )
        atomic_write_outputs(
            jsonl_path=output_dir / JSONL_NAME,
            jsonl_bytes=jsonl_bytes,
            manifest_path=output_dir / MANIFEST_NAME,
            manifest_bytes=_manifest_bytes(manifest),
        )
        _print_report(
            source_count=len(sources),
            records=records,
            manifest=manifest,
        )
        return 0
    except (AgentDocBuildError, ChunkingError, OSError, UnicodeError, ValueError) as exc:
        print(f"Agent doc chunk build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

