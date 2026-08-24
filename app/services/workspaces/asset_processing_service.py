"""In-process parsing worker for Workspace assets."""

from app.db.models import WorkspaceAssetStatus
from app.repositories import workspace_asset_repository as asset_repository
from app.services.workspaces.asset_settings import load_workspace_asset_settings
from app.services.workspaces.parsers import parse_asset
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.storage import WorkspaceStorage


class AssetProcessingService:
    def __init__(self, storage: WorkspaceStorage | None = None) -> None:
        self.settings = load_workspace_asset_settings()
        self.storage = storage or WorkspaceStorage(self.settings)

    def process(self, asset_id: str) -> None:
        record = asset_repository.get_asset(asset_id)
        if record is None or record.status not in {WorkspaceAssetStatus.PROCESSING}:
            return
        try:
            if not record.storage_key:
                raise RuntimeError("Asset original storage key is missing")
            parsed = parse_asset(
                self.storage.path_for_download(record.storage_key),
                asset_id=record.id,
                media_type=record.media_type,
                original_filename=record.original_filename,
                settings=self.settings,
            )
            payload = parsed.to_dict()
            ParsedAsset.validate_payload(payload, record.id)
            parsed_key = f"{record.workspace_id}/assets/{record.id}/parsed.json"
            self.storage.write_json(parsed_key, payload)
            if not asset_repository.mark_ready(
                record.id,
                parsed_storage_key=parsed_key,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
            ):
                self.storage.delete(parsed_key)
        except Exception as exc:
            asset_repository.mark_failed(
                record.id,
                error_code="invalid_asset_content" if isinstance(exc, (ValueError, UnicodeError)) else "storage_operation_failed",
                error_message=str(exc),
                expected_status="PROCESSING",
            )


def process_workspace_asset(asset_id: str) -> None:
    AssetProcessingService().process(asset_id)
