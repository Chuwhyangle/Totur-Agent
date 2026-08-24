"""Safe, atomic filesystem storage for Workspace assets and artifacts."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO
from uuid import uuid4

from app.services.workspaces.asset_settings import WorkspaceAssetSettings


MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
}


class WorkspaceStorageError(RuntimeError):
    """A Workspace storage operation failed safely."""


class InvalidWorkspaceFilename(WorkspaceStorageError):
    """The supplied filename is not a single safe filename."""


class UnsupportedWorkspaceAssetType(WorkspaceStorageError):
    """The filename, MIME type, or leading bytes are not supported."""


class InvalidWorkspaceAssetContent(WorkspaceStorageError):
    """The upload type is supported but its bytes are invalid."""


class WorkspaceAssetTooLarge(WorkspaceStorageError):
    """The upload exceeded the configured byte limit."""


@dataclass(frozen=True)
class StagedWorkspaceFile:
    staging_key: str
    extension: str
    size_bytes: int
    content_hash: str


class WorkspaceStorage:
    """Keep all user-controlled files below one configured root."""

    def __init__(self, settings: WorkspaceAssetSettings | None = None) -> None:
        from app.services.workspaces.asset_settings import load_workspace_asset_settings

        self.settings = settings or load_workspace_asset_settings()
        self.root_path = self.settings.root_path

    def stage_upload(
        self,
        file_stream: BinaryIO,
        *,
        workspace_id: str,
        asset_id: str,
        original_filename: str,
        media_type: str,
    ) -> StagedWorkspaceFile:
        extension = self.validate_filename_and_media_type(original_filename, media_type)
        staging_key = f"_staging/assets/{workspace_id}/{asset_id}.part"
        part_path = self.resolve(staging_key)
        size = 0
        digest = hashlib.sha256()
        leading = bytearray()
        completed = False
        try:
            self._prepare_parent(part_path)
            with part_path.open("xb") as output:
                while True:
                    chunk = file_stream.read(self.settings.write_chunk_bytes)
                    if chunk is None or not isinstance(chunk, (bytes, bytearray)):
                        raise WorkspaceStorageError("Upload stream did not return bytes")
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.settings.max_bytes:
                        raise WorkspaceAssetTooLarge("Workspace asset is too large")
                    if len(leading) < 8:
                        leading.extend(chunk[: 8 - len(leading)])
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            self._validate_content(extension, bytes(leading), part_path, media_type)
            completed = True
            return StagedWorkspaceFile(staging_key, extension, size, digest.hexdigest())
        except (WorkspaceStorageError, InvalidWorkspaceFilename, UnsupportedWorkspaceAssetType):
            raise
        except Exception as exc:
            raise WorkspaceStorageError("Workspace asset could not be staged") from exc
        finally:
            if not completed and 'part_path' in locals() and part_path.exists():
                try:
                    part_path.unlink()
                except OSError as exc:
                    raise WorkspaceStorageError("Staging file could not be cleaned up") from exc

    def promote(self, staging_key: str, final_key: str) -> None:
        source = self.resolve(staging_key)
        target = self.resolve(final_key)
        if target.exists() or target.is_symlink():
            raise WorkspaceStorageError("Workspace storage target already exists")
        try:
            self._prepare_parent(target)
            os.replace(source, target)
        except OSError as exc:
            raise WorkspaceStorageError("Workspace asset could not be moved") from exc

    def write_json(self, storage_key: str, payload: dict[str, object]) -> None:
        final_path = self.resolve(storage_key)
        part_path = final_path.with_name(f"{final_path.name}.{uuid4().hex}.part")
        try:
            self._prepare_parent(final_path)
            with part_path.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(part_path, final_path)
        except WorkspaceStorageError:
            raise
        except Exception as exc:
            raise WorkspaceStorageError("Workspace JSON could not be stored") from exc
        finally:
            if part_path.exists():
                part_path.unlink(missing_ok=True)

    def stage_bytes(self, storage_key: str, content: bytes) -> tuple[int, str]:
        if len(content) > self.settings.max_bytes:
            raise WorkspaceAssetTooLarge("Workspace artifact is too large")
        path = self.resolve(storage_key)
        try:
            self._prepare_parent(path)
            with path.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            return len(content), hashlib.sha256(content).hexdigest()
        except WorkspaceStorageError:
            raise
        except Exception as exc:
            raise WorkspaceStorageError("Workspace artifact could not be stored") from exc

    def delete(self, storage_key: str) -> None:
        path = self.resolve(storage_key)
        try:
            if path.is_symlink():
                raise WorkspaceStorageError("Symlink storage targets are not allowed")
            path.unlink(missing_ok=True)
        except WorkspaceStorageError:
            raise
        except OSError as exc:
            raise WorkspaceStorageError("Workspace file could not be deleted") from exc

    def exists(self, storage_key: str) -> bool:
        return self.resolve(storage_key).is_file()

    def path_for_download(self, storage_key: str) -> Path:
        path = self.resolve(storage_key)
        if not path.is_file() or path.is_symlink():
            raise WorkspaceStorageError("Workspace file does not exist")
        return path

    def resolve(self, storage_key: str) -> Path:
        if not storage_key or not storage_key.strip() or "\x00" in storage_key or "\\" in storage_key:
            raise WorkspaceStorageError("Invalid Workspace storage key")
        posix = PurePosixPath(storage_key)
        windows = PureWindowsPath(storage_key)
        if posix.is_absolute() or windows.is_absolute() or windows.drive or any(
            part in {"", ".", ".."} for part in posix.parts
        ):
            raise WorkspaceStorageError("Invalid Workspace storage key")
        candidate = self.root_path.joinpath(*posix.parts)
        self._reject_symlink_components(candidate)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root_path)
        except ValueError as exc:
            raise WorkspaceStorageError("Workspace storage key escapes root") from exc
        return resolved

    @staticmethod
    def validate_filename_and_media_type(filename: str, media_type: str) -> str:
        if not filename or not filename.strip() or "\x00" in filename:
            raise InvalidWorkspaceFilename("Workspace filename is invalid")
        name = filename.strip()
        windows = PureWindowsPath(name)
        if "/" in name or "\\" in name or name in {".", ".."} or windows.is_absolute() or windows.drive:
            raise InvalidWorkspaceFilename("Workspace filename must be a single file name")
        extension = Path(name).suffix.lower()
        expected = MEDIA_TYPES.get(extension)
        if expected is None:
            raise UnsupportedWorkspaceAssetType("Unsupported Workspace asset type")
        if media_type.strip().lower() != expected:
            raise UnsupportedWorkspaceAssetType("Filename and MIME type do not match")
        return extension

    @staticmethod
    def _validate_content(extension: str, leading: bytes, path: Path, media_type: str) -> None:
        if extension == ".pdf":
            if not leading.startswith(b"%PDF-"):
                raise InvalidWorkspaceAssetContent("Invalid PDF content")
            try:
                import pymupdf

                document = pymupdf.open(path)
                document.close()
            except Exception as exc:
                raise InvalidWorkspaceAssetContent("Invalid PDF content") from exc
        else:
            try:
                path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                raise InvalidWorkspaceAssetContent("Text asset must be UTF-8") from exc

    def _prepare_parent(self, path: Path) -> None:
        self._reject_symlink_components(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)

    def _reject_symlink_components(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root_path)
        except ValueError as exc:
            raise WorkspaceStorageError("Path is outside Workspace root") from exc
        current = self.root_path
        if current.is_symlink():
            raise WorkspaceStorageError("Workspace root must not be a symlink")
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise WorkspaceStorageError("Symlink storage components are not allowed")
