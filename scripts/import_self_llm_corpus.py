"""Import a fixed self-llm Git commit into the local Markdown corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.external_corpus_importer import (  # noqa: E402
    GitTreeEntry,
    ImportResult,
    import_corpus,
)

DEFAULT_REPOSITORY_URL = "https://github.com/datawhalechina/self-llm.git"
DEFAULT_REF = "42c1bff4334f4c21c33e5791f29e9cdca5d47c61"
DEFAULT_REPOSITORY_PATH = Path("external/self-llm.git")


def run_git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    """Run Git against a bare repository, or execute clone before it exists."""

    if args and args[0] == "clone":
        command = ["git", *args]
    else:
        command = ["git", f"--git-dir={repo}", *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        input=input_bytes,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git command failed: {' '.join(command)}; {detail}")
    return completed.stdout


def ensure_repository(repo: Path, ref: str, repository_url: str) -> None:
    """Create the partial bare clone once, otherwise fetch the requested ref."""

    if repo.exists():
        if not repo.is_dir():
            raise ValueError(f"Git repository path is not a directory: {repo}")
        run_git(repo, "fetch", "--filter=blob:none", "origin", ref)
        return

    repo.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        repo,
        "clone",
        "--bare",
        "--filter=blob:none",
        "--no-checkout",
        repository_url,
        str(repo),
    )


def hydrate_blobs(repo: Path, shas: Iterable[str]) -> None:
    """Fetch all selected blobs from a partial clone in one request."""

    unique_shas = sorted(set(shas))
    if not unique_shas:
        return
    run_git(
        repo,
        "fetch",
        "origin",
        "--no-tags",
        "--no-write-fetch-head",
        "--recurse-submodules=no",
        "--filter=blob:none",
        "--stdin",
        input_bytes=("\n".join(unique_shas) + "\n").encode("ascii"),
    )


def resolve_commit(repo: Path, ref: str) -> str:
    """Resolve a ref to a complete commit SHA."""

    output = run_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    commit = output.decode("ascii").strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError(f"Git ref did not resolve to a full commit SHA: {ref}")
    return commit


def read_tree_entries(repo: Path, commit: str) -> list[tuple[str, str]]:
    """Read Markdown blob references from a commit tree."""

    return [
        (path, sha)
        for path, sha, object_type in _read_tree_records(repo, commit)
        if object_type == "blob" and path.lower().endswith(".md")
    ]


def read_license(repo: Path, commit: str) -> bytes:
    """Read the exact root LICENSE blob from a commit tree."""

    for path, sha, object_type in _read_tree_records(repo, commit):
        if object_type == "blob" and path == "LICENSE":
            return read_blob(repo, sha)
    raise ValueError("upstream commit does not contain a root LICENSE")


def read_blob(repo: Path, sha: str) -> bytes:
    """Read one Git blob without checking out the repository."""

    return run_git(repo, "cat-file", "blob", sha)


def _read_tree_records(repo: Path, commit: str) -> list[tuple[str, str, str]]:
    raw = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", commit)
    records: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        header, separator, raw_path = record.partition(b"\t")
        if not separator:
            raise ValueError("malformed NUL-delimited Git tree record")
        fields = header.split()
        if len(fields) != 3:
            raise ValueError("malformed Git tree header")
        mode, raw_type, raw_sha = fields
        path = raw_path.decode("utf-8")
        object_type = raw_type.decode("ascii")
        sha = raw_sha.decode("ascii")
        records.append((path, sha, object_type))
    return records


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--repository-url", default=DEFAULT_REPOSITORY_URL)
    args = parser.parse_args(list(argv) if argv is not None else None)

    project_root = args.project_root.resolve()
    repo = project_root / DEFAULT_REPOSITORY_PATH
    try:
        ensure_repository(repo, args.ref, args.repository_url)
        commit = resolve_commit(repo, args.ref)
        tree_entries = read_tree_entries(repo, commit)
        hydrate_blobs(repo, (sha for _, sha in tree_entries))
        entries = [
            GitTreeEntry(path, read_blob(repo, sha))
            for path, sha in tree_entries
        ]
        result: ImportResult = import_corpus(
            project_root=project_root,
            commit_sha=commit,
            repository_url=args.repository_url,
            license_name="Apache-2.0",
            license_bytes=read_license(repo, commit),
            entries=entries,
        )
    except (RuntimeError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"self-llm corpus import failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"self-llm corpus imported: commit={commit} "
        f"files={result.manifest['markdown_file_count']} "
        f"manifest={result.target_path / 'corpus_manifest.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())