"""Format saved interview JDs into an injectable prompt context.

FR-2：私人 JD 从「工具」降级为「AgentContext 注入槽」。
意图确定、量小（当前 4 条 ≈ 4K tokens），全量注入优于检索。
"""

from __future__ import annotations

from typing import Iterable

from app.db.models import InterviewJDRecord


PRIVATE_JD_CONTEXT_MAX_CHARS = 4000


def _join(values: Iterable[str] | None) -> str:
    """Join a list field with 、, stripping blanks."""

    if not values:
        return ""
    return "、".join(str(value).strip() for value in values if str(value).strip())


def format_private_jd_context(
    records: Iterable[InterviewJDRecord],
    max_chars: int = PRIVATE_JD_CONTEXT_MAX_CHARS,
) -> str | None:
    """Format interview JD records into a Markdown context block.

    按 updated_at 倒序（list_all_interview_jds 已排序），超限截断。
    无记录时返回 None（不注入空段落）。
    """

    ordered = sorted(
        records,
        key=lambda record: (record.updated_at, record.id),
        reverse=True,
    )
    if not ordered:
        return None

    sections: list[str] = []
    for index, record in enumerate(ordered, start=1):
        header = f"### {index}. {record.title}"
        if record.role_family:
            header += f"｜{record.role_family}"
        if record.seniority:
            header += f"｜{record.seniority}"

        lines = [header]
        core_skills = _join(record.core_skills)
        if core_skills:
            lines.append(f"- 核心技能：{core_skills}")
        must_have = _join(record.must_have)
        if must_have:
            lines.append(f"- 必备：{must_have}")
        interview_focus = _join(record.interview_focus)
        if interview_focus:
            lines.append(f"- 面试重点：{interview_focus}")

        sections.append("\n".join(lines))

    body = "\n\n".join(sections)
    if not body.strip():
        return None

    prefix = f"## 用户关注的目标岗位（共 {len(ordered)} 条）\n\n"
    full = prefix + body

    if len(full) <= max_chars:
        return full

    # 超限：整体截断到 max_chars，保留头部说明。
    truncated = full[:max_chars].rstrip()
    return truncated