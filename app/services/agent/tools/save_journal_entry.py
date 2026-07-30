"""Save journal entry tool for Tutor Agent tool calling."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.repositories.journal_repository import create_journal_entry


def save_journal_entry(
    title: str,
    content: str,
    tags: str | None = None,
    entry_date: str | None = None,
) -> dict[str, Any]:
    """将日记内容保存到 journal_entries 表。

    Args:
        title: 日记标题。
        content: 日记内容（markdown 格式）。
        tags: 逗号分隔的标签，可选。
        entry_date: 日期 YYYY-MM-DD，可选，默认今天。

    Returns:
        保存结果的确认信息。
    """

    if not isinstance(title, str) or not title.strip():
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "title 必须是非空字符串。",
        }

    if not isinstance(content, str):
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "content 必须是字符串。",
        }

    safe_tags = tags.strip() if isinstance(tags, str) else ""
    safe_entry_date = entry_date.strip() if isinstance(entry_date, str) and entry_date.strip() else date.today().isoformat()

    try:
        record = create_journal_entry(
            title=title.strip(),
            content=content,
            entry_date=safe_entry_date,
            tags=safe_tags,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": "save_failed",
            "message": f"保存日记失败: {exc}",
        }

    return {
        "ok": True,
        "id": record.id,
        "title": record.title,
        "entry_date": record.entry_date,
        "tags": record.tags,
        "message": f"日记已保存（id={record.id}）：{record.title}",
    }
