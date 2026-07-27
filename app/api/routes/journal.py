"""Journal API 路由。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.db.models import JournalEntryRecord
from app.repositories.journal_repository import (
    create_journal_entry,
    delete_journal_entry,
    get_journal_entry,
    list_journal_entries,
    update_journal_entry,
)
from app.schemas.journal import (
    CreateJournalEntryRequest,
    JournalEntryItem,
    JournalEntryListResponse,
    UpdateJournalEntryRequest,
)


router = APIRouter(prefix="/journal", tags=["journal"])


def _item_from_record(record: JournalEntryRecord) -> JournalEntryItem:
    """把数据库记录转换成 API 响应对象。"""

    return JournalEntryItem(
        id=record.id,
        session_id=record.session_id,
        persona_id=record.persona_id,
        title=record.title,
        content=record.content,
        tags=record.tags,
        entry_date=record.entry_date,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/entries",
    response_model=JournalEntryListResponse,
)
def get_entries(
    date_filter: str | None = Query(default=None, alias="date", description="按日期过滤 YYYY-MM-DD"),
    tag: str | None = Query(default=None, description="按标签过滤"),
    limit: int = Query(default=50, ge=1, le=200),
) -> JournalEntryListResponse:
    """查询日记列表，支持按日期和标签过滤。"""

    records = list_journal_entries(date=date_filter, tag=tag, limit=limit)
    return JournalEntryListResponse(items=[_item_from_record(r) for r in records])


@router.get(
    "/entries/{entry_id}",
    response_model=JournalEntryItem,
)
def get_entry(entry_id: int) -> JournalEntryItem:
    """获取单条日记。"""

    record = get_journal_entry(entry_id)
    if record is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    return _item_from_record(record)


@router.post(
    "/entries",
    response_model=JournalEntryItem,
    status_code=status.HTTP_201_CREATED,
)
def create_entry(request: CreateJournalEntryRequest) -> JournalEntryItem:
    """创建一条日记。"""

    entry_date = request.entry_date or date.today().isoformat()
    record = create_journal_entry(
        title=request.title,
        content=request.content,
        entry_date=entry_date,
        session_id=request.session_id,
        persona_id=request.persona_id,
        tags=request.tags,
    )
    return _item_from_record(record)


@router.put(
    "/entries/{entry_id}",
    response_model=JournalEntryItem,
)
def update_entry(entry_id: int, request: UpdateJournalEntryRequest) -> JournalEntryItem:
    """更新一条日记。"""

    existing = get_journal_entry(entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="日记不存在")

    record = update_journal_entry(
        entry_id=entry_id,
        title=request.title,
        content=request.content,
        tags=request.tags,
        entry_date=request.entry_date,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    return _item_from_record(record)


@router.delete(
    "/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_entry(entry_id: int) -> None:
    """删除一条日记。"""

    deleted = delete_journal_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="日记不存在")
