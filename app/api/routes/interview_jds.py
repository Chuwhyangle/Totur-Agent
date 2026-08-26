"""Interview JD API 路由。"""

from fastapi import APIRouter, HTTPException, Query, status

from app.db.models import InterviewJDRecord
from app.repositories.interview_jd_repository import (
    create_interview_jd,
    delete_interview_jd,
    get_interview_jd,
    list_interview_jds,
    update_interview_jd,
)
from app.schemas.interview_jds import (
    CreateInterviewJDRequest,
    InterviewJDItem,
    InterviewJDListResponse,
    UpdateInterviewJDRequest,
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


@router.get("/interview-jds/{jd_id}", response_model=InterviewJDItem)
def get_interview_jd_record(
    jd_id: int,
    user_id: str = Query(..., min_length=1),
) -> InterviewJDItem:
    """获取指定用户保存的一条目标岗位 JD。"""

    record = get_interview_jd(jd_id=jd_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标岗位不存在")
    return _item_from_record(record)


@router.put("/interview-jds/{jd_id}", response_model=InterviewJDItem)
def update_interview_jd_record(
    jd_id: int,
    request: UpdateInterviewJDRequest,
    user_id: str | None = Query(default=None, min_length=1),
) -> InterviewJDItem:
    """更新指定用户保存的一条目标岗位 JD。"""

    # 优先使用查询参数；兼容直接复用创建请求体的旧客户端。
    effective_user_id = (user_id or request.user_id or "").strip()
    if not effective_user_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_id 不能为空")

    record = update_interview_jd(
        jd_id=jd_id,
        user_id=effective_user_id,
        **request.model_dump(exclude={"user_id"}),
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标岗位不存在")
    return _item_from_record(record)


@router.delete("/interview-jds/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview_jd_record(
    jd_id: int,
    user_id: str = Query(..., min_length=1),
) -> None:
    """删除指定用户保存的一条目标岗位 JD。"""

    deleted = delete_interview_jd(jd_id=jd_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标岗位不存在")


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
