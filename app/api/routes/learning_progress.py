"""用户级学习进度 API。"""

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.db.models import LearningProgressRecord
from app.schemas.learning_progress import (
    LearningProgressItem,
    LearningProgressListResponse,
    UpsertLearningProgressRequest,
)
from app.services.learning_progress_service import (
    InvalidLearningProgressError,
    LearningProgressService,
)


router = APIRouter(prefix="/learning-progress", tags=["learning-progress"])
learning_progress_service = LearningProgressService()


@router.get("", response_model=LearningProgressListResponse)
def list_progress(
    user_id: str = Query(..., min_length=1, max_length=64),
    subject: str = Query(default="sql", min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=100),
) -> LearningProgressListResponse:
    """读取用户在一个学习主题下的进度。"""

    try:
        records = learning_progress_service.list_for_user(
            user_id=user_id,
            subject=subject,
            limit=limit,
        )
    except InvalidLearningProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "invalid_learning_progress_query", "message": str(error)},
        ) from error

    return LearningProgressListResponse(
        user_id=user_id.strip(),
        subject=subject.strip().lower(),
        items=[_item_from_record(record) for record in records],
    )


@router.delete("/{progress_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_progress(
    progress_id: int = Path(..., ge=1),
    user_id: str = Query(..., min_length=1, max_length=64),
    subject: str = Query(default="sql", min_length=1, max_length=64),
) -> None:
    """删除属于当前用户的一条学习进度。"""

    try:
        deleted = learning_progress_service.delete_manual(
            progress_id=progress_id,
            user_id=user_id,
            subject=subject,
        )
    except InvalidLearningProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "invalid_learning_progress", "message": str(error)},
        ) from error
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习进度不存在")


@router.put("", response_model=LearningProgressItem)
def save_progress(
    request: UpsertLearningProgressRequest,
) -> LearningProgressItem:
    """新增或更新用户手动维护的一条学习进度。"""

    try:
        record = learning_progress_service.save_manual(
            user_id=request.user_id,
            subject=request.subject,
            topic=request.topic,
            level=request.level,
            status=request.status,
            evidence=request.evidence,
            next_step=request.next_step,
        )
    except InvalidLearningProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "invalid_learning_progress", "message": str(error)},
        ) from error
    return _item_from_record(record)


def _item_from_record(record: LearningProgressRecord) -> LearningProgressItem:
    """把数据库记录转换成 API 响应。"""

    return LearningProgressItem(
        id=record.id,
        user_id=record.user_id,
        subject=record.subject,
        topic=record.topic,
        level=record.level,
        status=record.status,
        evidence=record.evidence,
        next_step=record.next_step,
        source=record.source,
        updated_at=record.updated_at,
    )
