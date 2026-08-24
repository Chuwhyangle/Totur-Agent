"""Workspace Markdown Artifact creation, versioning, and reads."""

from datetime import datetime, timezone
import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.db.models import ArtifactRecord, ArtifactSourceRecord, ArtifactStatus, WorkspaceAssetStatus, WorkspaceTaskStatus
from app.repositories import workspace_artifact_repository as artifact_repository
from app.repositories import workspace_asset_repository as asset_repository
from app.repositories import workspace_task_repository as task_repository
from app.services.workspaces.asset_settings import load_workspace_asset_settings
from app.services.workspaces.storage import WorkspaceStorage
from app.services.workspaces.task_service import TaskNotFoundError, TaskService, TaskStateError, TaskValidationError
from app.services.workspaces.workspace_service import WorkspaceService


MAX_ARTIFACT_BYTES = 256 * 1024


class ArtifactError(ValueError):
    error_code = "artifact_error"


class ArtifactNotFoundError(ArtifactError):
    error_code = "artifact_not_found"


class ArtifactVersionConflictError(ArtifactError):
    error_code = "artifact_version_conflict"


class ArtifactValidationError(ArtifactError):
    error_code = "invalid_artifact"


class ArtifactService:
    def __init__(self, storage: WorkspaceStorage | None = None) -> None:
        settings = load_workspace_asset_settings()
        self.storage = storage or WorkspaceStorage(settings)
        self.workspace_service = WorkspaceService()
        self.task_service = TaskService()

    def create_artifact(self, *, user_id: str, workspace_id: str, task_id: str, created_by_step_id: int, tool_call_id: str, title: str, content: str, source_asset_ids: list[str] | tuple[str, ...] = (), supersedes_artifact_id: str | None = None) -> ArtifactRecord:
        self.workspace_service.require_active_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        task = self.task_service.get_owned_task(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if task.status is not WorkspaceTaskStatus.RUNNING:
            raise TaskStateError("Artifacts can only be created by running Tasks")
        step = task_repository.get_step(created_by_step_id)
        if step is None or step.task_id != task_id:
            raise ArtifactValidationError("created_by_step does not belong to Task")
        normalized_title = re.sub(r"\s+", " ", title.strip())
        if not normalized_title or len(normalized_title) > 255:
            raise ArtifactValidationError("Artifact title is invalid")
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_ARTIFACT_BYTES:
            raise ArtifactValidationError("Artifact content is too large")
        creation_key = f"{task_id}:{tool_call_id}"
        existing = artifact_repository.get_by_creation_key(creation_key)
        if existing:
            return existing

        source_ids = list(dict.fromkeys(source_asset_ids))
        for asset_id in source_ids:
            asset = asset_repository.get_asset(asset_id)
            if asset is None or asset.workspace_id != workspace_id or asset.status is WorkspaceAssetStatus.DELETED:
                raise ArtifactValidationError("Artifact source asset is invalid")

        version = 1
        series_id = None
        if supersedes_artifact_id:
            previous = artifact_repository.get_artifact(supersedes_artifact_id)
            if previous is None or previous.workspace_id != workspace_id or previous.status is not ArtifactStatus.READY:
                raise ArtifactVersionConflictError("Artifact predecessor is not READY in this Workspace")
            series_id = previous.artifact_series_id
            version = previous.version_number + 1
        artifact_id = str(uuid4())
        now = _now()
        record = ArtifactRecord(
            id=artifact_id, workspace_id=workspace_id, task_id=task_id, created_by_step_id=created_by_step_id,
            artifact_series_id=series_id or artifact_id, supersedes_artifact_id=supersedes_artifact_id,
            version_number=version, title=normalized_title, media_type="text/markdown", storage_key=None,
            size_bytes=None, content_hash=None, creation_key=creation_key, status=ArtifactStatus.CREATING,
            error_code=None, created_at=now, updated_at=now, deleted_at=None,
        )
        try:
            artifact_repository.create_artifact(record)
        except IntegrityError as exc:
            existing = artifact_repository.get_by_creation_key(creation_key)
            if existing:
                return existing
            raise ArtifactVersionConflictError("Artifact version conflicts with an existing revision") from exc

        staging_key = f"_staging/artifacts/{workspace_id}/{artifact_id}.part"
        final_key = f"{workspace_id}/artifacts/{artifact_id}/report.md"
        try:
            size_bytes, content_hash = self.storage.stage_bytes(staging_key, content_bytes)
            self.storage.promote(staging_key, final_key)
            for asset_id in source_ids:
                artifact_repository.insert_source(ArtifactSourceRecord(artifact_id=artifact_id, asset_id=asset_id, created_at=_now()))
            if not artifact_repository.mark_ready(artifact_id, storage_key=final_key, size_bytes=size_bytes, content_hash=content_hash):
                raise RuntimeError("Artifact status could not be finalized")
        except Exception as exc:
            self.storage.delete(staging_key)
            artifact_repository.mark_failed(artifact_id, error_code="artifact_storage_failed")
            raise ArtifactError("Artifact could not be created") from exc
        return artifact_repository.get_artifact(artifact_id) or record

    def get_artifact(self, *, user_id: str, workspace_id: str, artifact_id: str) -> ArtifactRecord:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        record = artifact_repository.get_artifact(artifact_id)
        if record is None or record.workspace_id != workspace_id:
            raise ArtifactNotFoundError("Artifact not found")
        return record

    def list_artifacts(self, *, user_id: str, workspace_id: str, limit: int = 50, include_versions: bool = False) -> list[ArtifactRecord]:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        records = artifact_repository.list_workspace_artifacts(workspace_id, limit=limit)
        if include_versions:
            return records
        latest: dict[str, ArtifactRecord] = {}
        for record in records:
            current = latest.get(record.artifact_series_id)
            if current is None or record.version_number > current.version_number:
                latest[record.artifact_series_id] = record
        return sorted(latest.values(), key=lambda item: (item.created_at, item.id), reverse=True)

    def read_content(self, *, user_id: str, workspace_id: str, artifact_id: str) -> tuple[ArtifactRecord, str]:
        record = self.get_artifact(user_id=user_id, workspace_id=workspace_id, artifact_id=artifact_id)
        if record.status is not ArtifactStatus.READY or not record.storage_key:
            raise ArtifactNotFoundError("Artifact content is not ready")
        try:
            return record, self.storage.path_for_download(record.storage_key).read_text(encoding="utf-8")
        except Exception as exc:
            raise ArtifactNotFoundError("Artifact content is unavailable") from exc

    def list_sources(self, artifact_id: str):
        return artifact_repository.list_sources(artifact_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
