"""FR-2: 私人 JD 上下文格式化与截断测试。"""

from __future__ import annotations

from app.db.models import InterviewJDRecord
from app.services.private_jd_context import (
    PRIVATE_JD_CONTEXT_MAX_CHARS,
    format_private_jd_context,
)


def _record(
    record_id: int,
    title: str,
    *,
    role_family: str | None = "ai_agent_engineer",
    seniority: str | None = "graduate",
    core_skills: list[str] | None = None,
    must_have: list[str] | None = None,
    interview_focus: list[str] | None = None,
    updated_at: str = "2026-07-04T00:00:00+00:00",
) -> InterviewJDRecord:
    return InterviewJDRecord(
        id=record_id,
        user_id="alice",
        title=title,
        role_family=role_family,
        seniority=seniority,
        target_graduation_years=["2025", "2026"],
        raw_text="raw",
        responsibilities=["职责"],
        must_have=must_have if must_have is not None else ["Python 基础"],
        core_skills=core_skills if core_skills is not None else ["LangChain"],
        preferred_skills=["RAG"],
        bonus_skills=[],
        keywords=["Agent"],
        interview_focus=interview_focus if interview_focus is not None else ["Agent 工具调用"],
        created_at="2026-07-04T00:00:00+00:00",
        updated_at=updated_at,
    )


def test_format_private_jd_context_returns_none_for_empty_records():
    assert format_private_jd_context([]) is None


def test_format_private_jd_context_builds_markdown_block():
    records = [_record(1, "AI Agent / LLM 应用开发岗位")]
    result = format_private_jd_context(records)

    assert result is not None
    assert "## 用户关注的目标岗位（共 1 条）" in result
    assert "### 1. AI Agent / LLM 应用开发岗位｜ai_agent_engineer｜graduate" in result
    assert "- 核心技能：LangChain" in result
    assert "- 必备：Python 基础" in result
    assert "- 面试重点：Agent 工具调用" in result


def test_format_private_jd_context_omits_empty_fields():
    records = [
        _record(
            1,
            "纯标题岗位",
            role_family=None,
            seniority=None,
            core_skills=[],
            must_have=[],
            interview_focus=[],
        )
    ]
    result = format_private_jd_context(records)

    assert result is not None
    assert "### 1. 纯标题岗位" in result
    assert "核心技能" not in result
    assert "必备" not in result
    assert "面试重点" not in result


def test_format_private_jd_context_orders_by_updated_at_desc():
    records = [
        _record(1, "旧岗位", updated_at="2026-07-01T00:00:00+00:00"),
        _record(2, "新岗位", updated_at="2026-07-05T00:00:00+00:00"),
    ]
    result = format_private_jd_context(records)

    assert result is not None
    assert result.index("新岗位") < result.index("旧岗位")
    assert "## 用户关注的目标岗位（共 2 条）" in result


def test_format_private_jd_context_truncates_over_max_chars():
    long_skills = ["技能" * 100 for _ in range(50)]
    records = [_record(1, "超长岗位", core_skills=long_skills)]
    result = format_private_jd_context(records)

    assert result is not None
    assert len(result) <= PRIVATE_JD_CONTEXT_MAX_CHARS
    assert result.startswith("## 用户关注的目标岗位")


def test_private_jd_context_max_chars_constant_is_positive():
    assert PRIVATE_JD_CONTEXT_MAX_CHARS > 0