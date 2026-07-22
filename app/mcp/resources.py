"""MCP resources backed by Tutor Agent project assets."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from app.mcp.settings import get_project_root
from app.services.index_manifest import ManifestError, load_manifest
from app.services.rag_settings import CHROMA_PERSIST_DIR
from app.services.tool_metrics import tool_metrics_snapshot

def _project_root() -> Path:
    return get_project_root()

def manifest_resource_payload() -> dict[str, Any]:
    manifest_dir = _project_root() / CHROMA_PERSIST_DIR
    paths = sorted(manifest_dir.glob("index_manifest*.json"))
    if not paths:
        return {"ok": False, "error": "manifest_not_found", "message": "No index manifest exists. Build the knowledge index first.", "manifests": []}
    manifests: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            payload = load_manifest(path).to_dict()
            payload["file"] = path.name
            manifests.append(payload)
        except ManifestError as exc:
            errors.append({"file": path.name, "message": str(exc)})
    return {"ok": not errors, "count": len(manifests), "manifests": manifests, "errors": errors}

def list_project_files(relative_dir: str, suffixes: tuple[str, ...], uri_prefix: str) -> list[dict[str, str | int]]:
    root = _project_root() / relative_dir
    if not root.is_dir():
        return []
    items: list[dict[str, str | int]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in suffixes:
            continue
        relative_path = path.relative_to(root).as_posix()
        items.append({"path": relative_path, "name": path.name, "bytes": path.stat().st_size, "uri": f"{uri_prefix}/{quote(relative_path, safe='')}"})
    return items

def docs_catalog_payload() -> dict[str, Any]:
    items = list_project_files("docs", (".md",), "docs://content")
    return {"ok": True, "count": len(items), "items": items}

def reports_catalog_payload() -> dict[str, Any]:
    items = list_project_files("reports", (".md", ".json", ".jsonl"), "reports://content")
    return {"ok": True, "count": len(items), "items": items}

def read_project_file(relative_dir: str, encoded_path: str) -> str:
    relative_path = unquote(encoded_path)
    root = (_project_root() / relative_dir).resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise FileNotFoundError(f"resource path escapes {relative_dir}: {relative_path}")
    if not candidate.is_file():
        raise FileNotFoundError(f"resource not found: {relative_dir}/{relative_path}")
    return candidate.read_text(encoding="utf-8")

def manifest_state_signature() -> tuple[tuple[str, int, int], ...]:
    tracked: list[tuple[str, int, int]] = []
    for relative_dir, patterns in ((CHROMA_PERSIST_DIR, ("index_manifest*.json",)), ("docs", ("*.md",)), ("reports", ("*.md", "*.json", "*.jsonl"))):
        root = _project_root() / relative_dir
        for pattern in patterns:
            for path in root.rglob(pattern) if root.exists() else ():
                stat = path.stat()
                tracked.append((path.relative_to(_project_root()).as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(tracked))

def json_resource(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

def metrics_resource_payload() -> dict[str, Any]:
    return tool_metrics_snapshot()
