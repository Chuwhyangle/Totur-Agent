"""Workspace Asset upload, lifecycle, and download API."""

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.db.models import WorkspaceAssetRecord
from app.schemas.workspace_assets import WorkspaceAssetItem, WorkspaceAssetListResponse, WorkspaceAssetUploadResponse
from app.services.workspaces.asset_processing_service import process_workspace_asset
from app.services.workspaces.asset_service import (
    AssetDuplicateError,
    AssetInUseError,
    AssetNotFoundError,
    AssetNotReadyError,
    AssetService,
    AssetStateError,
    WorkspaceAssetError,
)
from app.services.workspaces.storage import (
    InvalidWorkspaceFilename,
    UnsupportedWorkspaceAssetType,
    WorkspaceAssetTooLarge,
    InvalidWorkspaceAssetContent,
    WorkspaceStorageError,
)
from app.services.workspaces.workspace_service import WorkspaceArchivedError, WorkspaceNotFoundError


router = APIRouter(tags=["workspace-assets"])
asset_service = AssetService()


@router.post("/workspaces/{workspace_id}/assets", response_model=WorkspaceAssetUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_asset(workspace_id: str, response: Response, background_tasks: BackgroundTasks, user_id: str = Query(..., min_length=1), file: UploadFile = File(...)) -> WorkspaceAssetUploadResponse:
    try:
        record, duplicate = asset_service.upload(
            user_id=user_id,
            workspace_id=workspace_id,
            file_stream=file.file,
            original_filename=file.filename or "",
            media_type=file.content_type or "",
        )
        if not duplicate:
            background_tasks.add_task(process_workspace_asset, record.id)
        else:
            response.status_code = status.HTTP_200_OK
        return WorkspaceAssetUploadResponse(asset=_item(record), duplicate=duplicate)
    except (WorkspaceNotFoundError, AssetNotFoundError) as exc:
        raise _not_found() from exc
    except WorkspaceArchivedError as exc:
        raise _error(409, "workspace_archived", workspace_id) from exc
    except UnsupportedWorkspaceAssetType as exc:
        raise _error(415, "unsupported_asset_type", str(exc)) from exc
    except (InvalidWorkspaceFilename, InvalidWorkspaceAssetContent, ValueError, UnicodeError) as exc:
        raise _error(422, "invalid_asset_content", str(exc)) from exc
    except WorkspaceAssetTooLarge as exc:
        raise _error(413, "asset_too_large", str(exc)) from exc
    except WorkspaceStorageError as exc:
        raise _error(500, "storage_operation_failed", str(exc)) from exc


@router.get("/workspaces/{workspace_id}/assets", response_model=WorkspaceAssetListResponse)
def list_assets(workspace_id: str, user_id: str = Query(..., min_length=1), asset_status: str | None = Query(default=None, alias="status"), media_type: str | None = None, limit: int = Query(default=50, ge=1, le=100)) -> WorkspaceAssetListResponse:
    try:
        records = asset_service.list_assets(user_id=user_id, workspace_id=workspace_id, status=asset_status, media_type=media_type, limit=limit)
    except WorkspaceNotFoundError as exc:
        raise _not_found() from exc
    return WorkspaceAssetListResponse(items=[_item(record) for record in records])


@router.get("/workspaces/{workspace_id}/assets/{asset_id}", response_model=WorkspaceAssetItem)
def get_asset(workspace_id: str, asset_id: str, user_id: str = Query(..., min_length=1)) -> WorkspaceAssetItem:
    try:
        return _item(asset_service.get_asset(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id))
    except (WorkspaceNotFoundError, AssetNotFoundError) as exc:
        raise _not_found() from exc


@router.get("/workspaces/{workspace_id}/assets/{asset_id}/download")
def download_asset(workspace_id: str, asset_id: str, user_id: str = Query(..., min_length=1)):
    try:
        record, path = asset_service.download_path(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id)
    except (WorkspaceNotFoundError, AssetNotFoundError) as exc:
        raise _not_found() from exc
    except (AssetNotReadyError, WorkspaceStorageError) as exc:
        raise _error(409, "asset_not_ready", str(exc)) from exc
    return FileResponse(path, media_type=record.media_type, filename=_download_filename(record.original_filename))


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/retry", response_model=WorkspaceAssetItem, status_code=status.HTTP_202_ACCEPTED)
def retry_asset(workspace_id: str, asset_id: str, background_tasks: BackgroundTasks, user_id: str = Query(..., min_length=1)) -> WorkspaceAssetItem:
    try:
        record = asset_service.retry(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id)
        background_tasks.add_task(process_workspace_asset, record.id)
        return _item(record)
    except (WorkspaceNotFoundError, AssetNotFoundError) as exc:
        raise _not_found() from exc
    except WorkspaceArchivedError as exc:
        raise _error(409, "workspace_archived", workspace_id) from exc
    except AssetStateError as exc:
        raise _error(409, "asset_processing_interrupted", str(exc)) from exc


@router.delete("/workspaces/{workspace_id}/assets/{asset_id}", response_model=WorkspaceAssetItem)
def delete_asset(workspace_id: str, asset_id: str, user_id: str = Query(..., min_length=1)) -> WorkspaceAssetItem:
    try:
        return _item(asset_service.delete(user_id=user_id, workspace_id=workspace_id, asset_id=asset_id))
    except (WorkspaceNotFoundError, AssetNotFoundError) as exc:
        raise _not_found() from exc
    except WorkspaceArchivedError as exc:
        raise _error(409, "workspace_archived", workspace_id) from exc
    except AssetInUseError as exc:
        raise _error(409, "asset_in_use", str(exc)) from exc
    except AssetStateError as exc:
        raise _error(409, "invalid_asset_state", str(exc)) from exc


def _item(record: WorkspaceAssetRecord) -> WorkspaceAssetItem:
    return WorkspaceAssetItem(
        id=record.id, workspace_id=record.workspace_id, original_filename=record.original_filename,
        media_type=record.media_type, size_bytes=record.size_bytes, content_hash=record.content_hash,
        status=record.status, parser_name=record.parser_name, parser_version=record.parser_version,
        error_code=record.error_code, error_message=record.error_message, created_at=record.created_at,
        updated_at=record.updated_at, deleted_at=record.deleted_at,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Asset not found")


def _error(code: str | int, message: str, extra: str | None = None) -> HTTPException:
    status_code = code if isinstance(code, int) else 422
    detail = {"error": message, "message": extra or message}
    return HTTPException(status_code=status_code, detail=detail)


def _download_filename(filename: str) -> str:
    return filename.replace("\r", "").replace("\n", "").replace('"', "'")
