"""Bounded startup recovery for interrupted Workspace Asset operations."""

from datetime import datetime, timedelta, timezone

from app.db.models import WorkspaceAssetStatus
from app.repositories import workspace_asset_repository as asset_repository
from app.services.workspaces.asset_settings import load_workspace_asset_settings
from app.services.workspaces.asset_processing_service import AssetProcessingService
from app.services.workspaces.storage import WorkspaceStorage


class AssetRecoveryService:
    def __init__(self) -> None:
        self.settings = load_workspace_asset_settings()
        self.storage = WorkspaceStorage(self.settings)

    def recover_once(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.settings.processing_stale_seconds)).isoformat()
        for record in asset_repository.list_stale_assets(cutoff, limit=self.settings.recovery_batch_size):
            try:
                if record.status is WorkspaceAssetStatus.STAGING:
                    if not record.storage_key:
                        extension = "." + record.original_filename.rsplit(".", 1)[-1].lower()
                        final_key = f"{record.workspace_id}/assets/{record.id}/original{extension}"
                        self.storage.promote(f"_staging/assets/{record.workspace_id}/{record.id}.part", final_key)
                        asset_repository.mark_processing(record.id, storage_key=final_key)
                    else:
                        asset_repository.mark_processing(record.id, storage_key=record.storage_key)
                    AssetProcessingService(self.storage).process(record.id)
                elif record.status is WorkspaceAssetStatus.PROCESSING:
                    asset_repository.mark_failed(record.id, error_code="asset_processing_interrupted", expected_status="PROCESSING")
                elif record.status is WorkspaceAssetStatus.DELETING:
                    for key in (record.storage_key, record.parsed_storage_key):
                        if key:
                            self.storage.delete(key)
                    asset_repository.mark_deleted(record.id)
            except Exception:
                # One broken record must not prevent other records from recovery.
                continue


def recover_workspace_assets_once() -> None:
    AssetRecoveryService().recover_once()
