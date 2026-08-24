"""Workspace Asset application service."""

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.db.models import WorkspaceAssetRecord, WorkspaceAssetStatus, WorkspaceStatus
from app.repositories import workspace_asset_repository as asset_repository
from app.services.workspaces import workspace_service
from app.services.workspaces.asset_settings import load_workspace_asset_settings
from app.services.workspaces.parsers import parse_asset
from app.services.workspaces.storage import (
    WorkspaceStorage,
    WorkspaceStorageError,
)


class WorkspaceAssetError(ValueError):
    """Base error for Workspace Asset use cases."""

    error_code = "workspace_asset_error"


class AssetNotFoundError(WorkspaceAssetError):
    error_code = "asset_not_found"


class AssetNotReadyError(WorkspaceAssetError):
    error_code = "asset_not_ready"


class AssetDuplicateError(WorkspaceAssetError):
    error_code = "asset_duplicate"


class AssetInUseError(WorkspaceAssetError):
    error_code = "asset_in_use"


class AssetStateError(WorkspaceAssetError):
    error_code = "invalid_asset_state"


class AssetLimitError(WorkspaceAssetError):
    error_code = "asset_limit_reached"


class AssetService:
    def __init__(self, storage: WorkspaceStorage | None = None) -> None:
        self.settings = load_workspace_asset_settings()
        self.storage = storage or WorkspaceStorage(self.settings)
        self.workspace_service = workspace_service.WorkspaceService()

    def upload(
        self,
        *,
        user_id: str,
        workspace_id: str,
        file_stream,
        original_filename: str,
        media_type: str,
    ) -> tuple[WorkspaceAssetRecord, bool]:
        workspace = self.workspace_service.require_active_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        if asset_repository.count_active_assets(workspace.id) >= self.settings.max_files:
            raise AssetLimitError("Workspace asset limit reached")

        asset_id = str(uuid4())
        staged = self.storage.stage_upload(
            file_stream,
            workspace_id=workspace.id,
            asset_id=asset_id,
            original_filename=original_filename,
            media_type=media_type,
        )
        try:
            # Validate CSV/JSON/PDF content before creating a visible asset record.
            parse_asset(
                self.storage.resolve(staged.staging_key),
                asset_id=asset_id,
                media_type=media_type,
                original_filename=original_filename,
                settings=self.settings,
            )
            now = _now()
            record = WorkspaceAssetRecord(
                id=asset_id,
                workspace_id=workspace.id,
                original_filename=original_filename.strip(),
                media_type=media_type.strip().lower(),
                size_bytes=staged.size_bytes,
                storage_key=None,
                parsed_storage_key=None,
                content_hash=staged.content_hash,
                dedupe_key=staged.content_hash,
                status=WorkspaceAssetStatus.STAGING,
                parser_name=None,
                parser_version=None,
                error_code=None,
                error_message=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            try:
                asset_repository.insert_staging_asset(record)
            except IntegrityError:
                duplicate = asset_repository.get_active_asset_by_hash(workspace.id, staged.content_hash)
                if duplicate is not None:
                    self.storage.delete(staged.staging_key)
                    return duplicate, True
                raise

            final_key = f"{workspace.id}/assets/{asset_id}/original{staged.extension}"
            try:
                self.storage.promote(staged.staging_key, final_key)
                if not asset_repository.mark_processing(asset_id, storage_key=final_key):
                    raise WorkspaceStorageError("Asset status could not be claimed")
            except Exception:
                asset_repository.mark_failed(asset_id, error_code="storage_operation_failed", expected_status="STAGING")
                raise
            return asset_repository.get_asset(asset_id) or record, False
        except Exception:
            # A duplicate has no database row for this upload, so its staging file
            # is cleaned here. A stored asset keeps its original file for retry.
            self.storage.delete(staged.staging_key)
            raise

    def list_assets(self, *, user_id: str, workspace_id: str, status: str | None = None, media_type: str | None = None, limit: int = 50) -> list[WorkspaceAssetRecord]:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        return asset_repository.list_workspace_assets(workspace_id, status=status, media_type=media_type, limit=limit)

    def get_asset(self, *, user_id: str, workspace_id: str, asset_id: str) -> WorkspaceAssetRecord:
        self.workspace_service.get_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        record = asset_repository.get_owned_asset(asset_id, user_id)
        if record is None or record.workspace_id != workspace_id:
            raise AssetNotFoundError("Asset not found")
        return record

    def retry(self, *, user_id: str, workspace_id: str, asset_id: str) -> WorkspaceAssetRecord:
        self.workspace_service.require_active_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        record = self.get_asset(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id)
        if record.status is not WorkspaceAssetStatus.FAILED or not record.storage_key:
            raise AssetStateError("Only FAILED assets with original files can be retried")
        if not asset_repository.claim_retry(asset_id):
            raise AssetStateError("Asset could not be retried")
        return asset_repository.get_asset(asset_id) or record

    def delete(self, *, user_id: str, workspace_id: str, asset_id: str) -> WorkspaceAssetRecord:
        self.workspace_service.require_active_owned_workspace(user_id=user_id, workspace_id=workspace_id)
        record = self.get_asset(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id)
        if record.status is WorkspaceAssetStatus.DELETED:
            return record
        if asset_repository.is_asset_used_by_running_task(asset_id):
            raise AssetInUseError("Asset is referenced by a running task")
        if record.status not in {WorkspaceAssetStatus.READY, WorkspaceAssetStatus.FAILED}:
            raise AssetStateError("Asset cannot be deleted in its current state")
        if not asset_repository.claim_delete(asset_id):
            raise AssetStateError("Asset could not be marked for deletion")
        try:
            for key in (record.storage_key, record.parsed_storage_key):
                if key:
                    self.storage.delete(key)
            asset_repository.mark_deleted(asset_id)
        except Exception:
            raise
        return asset_repository.get_asset(asset_id) or record

    def download_path(self, *, user_id: str, workspace_id: str, asset_id: str):
        record = self.get_asset(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id)
        if record.status is not WorkspaceAssetStatus.READY or not record.storage_key:
            raise AssetNotReadyError("Asset is not ready")
        return record, self.storage.path_for_download(record.storage_key)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
