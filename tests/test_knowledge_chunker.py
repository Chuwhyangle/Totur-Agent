"""学习笔记分块器的单元测试。"""

import pytest

from app.services.knowledge_chunker import chunk_markdown


def test_chunk_markdown_builds_title_paths_and_keeps_headings():
    chunks = chunk_markdown(
        text=(
            "# Agent 架构设计\n"
            "主流程说明。\n"
            "## 非目标\n"
            "不做复杂架构。\n"
            "### 测试策略\n"
            "小步测试。"
        ),
        source="docs/agent-architecture.md",
    )

    assert [chunk.title_path for chunk in chunks] == [
        "Agent 架构设计",
        "Agent 架构设计 > 非目标",
        "Agent 架构设计 > 非目标 > 测试策略",
    ]
    assert chunks[0].content.startswith("# Agent 架构设计")
    assert chunks[1].content.startswith("## 非目标")
    assert chunks[2].content.startswith("### 测试策略")


def test_chunk_markdown_skips_empty_heading_sections():
    chunks = chunk_markdown(
        text="# 空章节\n\n## 有内容\n这里是真正内容。",
        source="docs/demo.md",
    )

    assert len(chunks) == 1
    assert chunks[0].title_path == "空章节 > 有内容"
    assert chunks[0].content == "## 有内容\n这里是真正内容。"


def test_chunk_markdown_supports_documents_without_headings():
    chunks = chunk_markdown(
        text="没有标题的学习笔记也应该可以进入索引。",
        source="docs/plain.md",
    )

    assert len(chunks) == 1
    assert chunks[0].title_path == ""
    assert chunks[0].content == "没有标题的学习笔记也应该可以进入索引。"


def test_chunk_markdown_splits_long_content_with_overlap():
    text = "0123456789" * 7

    chunks = chunk_markdown(
        text=text,
        source="docs/long.md",
        chunk_size=30,
        chunk_overlap=5,
    )

    assert [chunk.content for chunk in chunks] == [
        text[0:30],
        text[25:55],
        text[50:70],
    ]
    assert chunks[0].content[-5:] == chunks[1].content[:5]
    assert chunks[1].content[-5:] == chunks[2].content[:5]


def test_chunk_markdown_repeats_heading_for_long_titled_sections():
    chunks = chunk_markdown(
        text="# 长章节\n" + ("0123456789" * 7),
        source="docs/long-heading.md",
        chunk_size=35,
        chunk_overlap=5,
    )

    assert len(chunks) > 1
    assert all(chunk.content.startswith("# 长章节\n") for chunk in chunks)
    assert all(len(chunk.content) <= 35 for chunk in chunks)


def test_chunk_markdown_uses_deterministic_chunk_ids():
    first_run = chunk_markdown(
        text="# 标题\n" + ("内容" * 80),
        source="docs/rebuild.md",
        chunk_size=40,
        chunk_overlap=10,
    )
    second_run = chunk_markdown(
        text="# 标题\n" + ("内容" * 80),
        source="docs/rebuild.md",
        chunk_size=40,
        chunk_overlap=10,
    )

    assert [chunk.chunk_id for chunk in first_run] == [
        chunk.chunk_id for chunk in second_run
    ]
    assert [chunk.chunk_id for chunk in first_run] == [
        f"docs/rebuild.md#{index}" for index in range(len(first_run))
    ]


def test_chunk_markdown_rejects_invalid_window_settings():
    with pytest.raises(ValueError, match="chunk_overlap must be smaller"):
        chunk_markdown(
            text="内容",
            source="docs/bad.md",
            chunk_size=10,
            chunk_overlap=10,
        )
