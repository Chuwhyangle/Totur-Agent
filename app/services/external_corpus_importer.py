"""Pure helpers for importing an external Markdown corpus."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
import re
import unicodedata
from typing import Iterable


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


def _normalize_component(component: str) -> str:
    safe = _INVALID_COMPONENT_CHARS.sub("_", component).rstrip(" .")
    if not safe:
        safe = "_"
    reserved_key = safe.split(".", 1)[0].upper()
    if reserved_key in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"
    return safe