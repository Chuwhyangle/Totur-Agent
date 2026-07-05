"""Interview JD API 路由。"""

from fastapi import APIRouter, Query, status

from app.db.models import InterviewJDRecord
from app.repositories.interview_jd_repository import (
    create_interview_jd,
    list_interview_jds,
)
from app.schemas.interview_jds import (
    CreateInterviewJDRequest,
    InterviewJDItem,
    InterviewJDListResponse,
)


router = APIRouter(tags=["interview-jds"])


@router.post(
    "/interview-jds",
    response_model=InterviewJDItem,
    status_code=status.HTTP_201_CREATED,
)
def create_interview_jd_record(request: CreateInterviewJDRequest) -> InterviewJDItem:
    """保存用户粘贴或整理后的目标岗位 JD。"""

    record = create_interview_jd(**request.model_dump())

    return _item_from_record(record)


@router.get("/interview-jds", response_model=InterviewJDListResponse)
def get_interview_jds(
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> InterviewJDListResponse:
    """查询某个用户保存的 JD 列表。"""

    records = list_interview_jds(user_id=user_id, limit=limit)

    return InterviewJDListResponse(
        user_id=user_id,
        items=[_item_from_record(record) for record in records],
    )


def _item_from_record(record: InterviewJDRecord) -> InterviewJDItem:
    """把数据库记录转换成 API 响应对象。"""

    return InterviewJDItem(
        id=record.id,
        user_id=record.user_id,
        title=record.title,
        role_family=record.role_family,
        seniority=record.seniority,
        target_graduation_years=record.target_graduation_years,
        raw_text=record.raw_text,
        responsibilities=record.responsibilities,
        must_have=record.must_have,
        core_skills=record.core_skills,
        preferred_skills=record.preferred_skills,
        bonus_skills=record.bonus_skills,
        keywords=record.keywords,
        interview_focus=record.interview_focus,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
