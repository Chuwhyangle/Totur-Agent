"""Pure helpers for importing an external Markdown corpus."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import unicodedata
from typing import Iterable
from uuid import uuid4


_INVALID_COMPONENT_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"|?*]')
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class GitTreeEntry:
    """One Git tree blob with its original UTF-8 path and bytes."""

    original_path: str
    content: bytes


@dataclass(frozen=True)
class ImportResult:
    """The installed snapshot and its validated JSON-compatible Manifest."""

    target_path: Path
    manifest: dict[str, object]


def normalize_git_path(original_path: str) -> str:
    """Return a stable, Windows-safe POSIX path below the corpus docs folder."""

    if not isinstance(original_path, str) or not original_path:
        raise ValueError("Git path must be a non-empty string")

    normalized = unicodedata.normalize("NFC", original_path).replace("\\", "/")
    if normalized.startswith("/") or _WINDOWS_DRIVE.match(normalized):
        raise ValueError("Git path must be relative")

    raw_parts = normalized.split("/")
    if any(part in {".", ".."} for part in raw_parts):
        raise ValueError("Git path cannot contain dot segments")

    safe_parts = [_normalize_component(part) for part in raw_parts]
    return PurePosixPath("docs", *safe_parts).as_posix()


def build_path_mapping(original_paths: Iterable[str]) -> dict[str, str]:
    """Map original paths to deterministic case-insensitive-safe output paths."""

    ordered_paths = sorted(original_paths)
    if len(ordered_paths) != len(set(ordered_paths)):
        raise ValueError("Git paths must be unique")

    candidates = {
        original_path: normalize_git_path(original_path)
        for original_path in ordered_paths
    }
    collision_counts: dict[str, int] = {}
    for candidate in candidates.values():
        key = candidate.casefold()
        collision_counts[key] = collision_counts.get(key, 0) + 1

    result: dict[str, str] = {}
    for original_path in ordered_paths:
        candidate = candidates[original_path]
        if collision_counts[candidate.casefold()] > 1:
            digest = hashlib.sha256(original_path.encode("utf-8")).hexdigest()[:8]
            path = PurePosixPath(candidate)
            candidate = path.with_name(
                f"{path.stem}--{digest}{path.suffix}"
            ).as_posix()
        result[original_path] = candidate

    folded = [path.casefold() for path in result.values()]
    if len(folded) != len(set(folded)):
        raise ValueError("normalized Git paths still collide")
    return result


def import_corpus(
    *,
    project_root: Path,
    commit_sha: str,
    repository_url: str,
    license_name: str,
    license_bytes: bytes,
    entries: Iterable[GitTreeEntry],
) -> ImportResult:
    """Stage and atomically install a Markdown-only external corpus snapshot."""

    _require_nonempty(commit_sha, "commit_sha")
    _require_nonempty(repository_url, "repository_url")
    _require_nonempty(license_name, "license_name")
    if not isinstance(license_bytes, bytes):
        raise TypeError("license_bytes must be bytes")
    license_bytes.decode("utf-8")

    markdown_entries = [
        entry
        for entry in entries
        if _is_markdown_entry(entry)
    ]
    if not markdown_entries:
        raise ValueError("no Markdown entries found")

    # Decode every file before creating staging or touching the existing target.
    for entry in markdown_entries:
        if not isinstance(entry.content, bytes):
            raise TypeError("Git entry content must be bytes")
        entry.content.decode("utf-8")

    mapping = build_path_mapping(entry.original_path for entry in markdown_entries)
    file_records = []
    for entry in markdown_entries:
        file_records.append(
            {
                "original_path": entry.original_path,
                "normalized_path": mapping[entry.original_path],
                "content_sha256": f"sha256:{hashlib.sha256(entry.content).hexdigest()}",
                "byte_count": len(entry.content),
            }
        )
    file_records.sort(key=lambda item: str(item["normalized_path"]))

    stable_payload = {
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "license": license_name,
        "files": file_records,
    }
    canonical = json.dumps(
        stable_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    manifest: dict[str, object] = {
        "schema_version": 1,
        "repository_url": repository_url,
        "commit_sha": commit_sha,
        "license": license_name,
        "markdown_file_count": len(file_records),
        "files": file_records,
        "fingerprint": fingerprint,
    }

    root = Path(project_root).resolve()
    corpus_root = root / "corpus"
    target = corpus_root / "self-llm"
    staging = corpus_root / f".self-llm-staging-{uuid4().hex}"
    backup = corpus_root / f".self-llm-backup-{uuid4().hex}"
    for candidate in (staging, target, backup):
        _assert_within(candidate, corpus_root)

    corpus_root.mkdir(parents=True, exist_ok=True)
    try:
        staging.mkdir(parents=True, exist_ok=False)
        (staging / "docs").mkdir(parents=True, exist_ok=True)
        (staging / ".gitattributes").write_bytes(b"* -text\n")
        for entry in markdown_entries:
            output = staging / PurePosixPath(mapping[entry.original_path])
            _assert_within(output, staging)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(entry.content)
        (staging / "LICENSE").write_bytes(license_bytes)
        manifest_path = staging / "corpus_manifest.json"
        manifest_text = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=2
        )
        with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(manifest_text + "\n")
        _verify_staging(staging, markdown_entries, mapping, manifest)
        _replace_target(staging, target, backup)
    except Exception:
        if staging.exists():
            _remove_path(staging)
        raise

    return ImportResult(target_path=target, manifest=manifest)


def _normalize_component(component: str) -> str:
    safe = _INVALID_COMPONENT_CHARS.sub("_", component).rstrip(" .")
    if not safe:
        safe = "_"
    reserved_key = safe.split(".", 1)[0].upper()
    if reserved_key in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"
    return safe


def _is_markdown_entry(entry: GitTreeEntry) -> bool:
    if not isinstance(entry, GitTreeEntry):
        raise TypeError("entries must contain GitTreeEntry records")
    return entry.original_path.lower().endswith(".md")


def _require_nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _assert_within(candidate: Path, parent: Path) -> None:
    candidate_resolved = candidate.resolve(strict=False)
    parent_resolved = parent.resolve(strict=False)
    try:
        candidate_resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes corpus root: {candidate}") from exc


def _verify_staging(
    staging: Path,
    entries: list[GitTreeEntry],
    mapping: dict[str, str],
    manifest: dict[str, object],
) -> None:
    for entry in entries:
        output = staging / PurePosixPath(mapping[entry.original_path])
        if output.read_bytes() != entry.content:
            raise OSError(f"staged file verification failed: {output}")
    actual = json.loads((staging / "corpus_manifest.json").read_text("utf-8"))
    if actual != manifest:
        raise OSError("staged Manifest verification failed")


def _replace_target(staging: Path, target: Path, backup: Path) -> None:
    old_moved = False
    new_moved = False
    try:
        if target.exists():
            shutil.move(str(target), str(backup))
            old_moved = True
        shutil.move(str(staging), str(target))
        new_moved = True
        if backup.exists():
            _remove_path(backup)
    except Exception:
        if target.exists() and (new_moved or backup.exists()):
            _remove_path(target)
        if backup.exists():
            shutil.move(str(backup), str(target))
        raise
    finally:
        if staging.exists():
            _remove_path(staging)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)