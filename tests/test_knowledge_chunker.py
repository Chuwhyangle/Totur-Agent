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


def test_chunk_markdown_prefers_sentence_boundaries_for_long_text():
    sentences = [
        f"第{index:02d}句用于验证知识库分块器会优先选择完整句号边界。"
        for index in range(1, 31)
    ]

    chunks = chunk_markdown(
        text="".join(sentences),
        source="docs/sentences.md",
    )

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 512 for chunk in chunks)
    assert all(chunk.content.endswith("。") for chunk in chunks[:-1])
    assert all(chunk.content.startswith(tuple(sentences)) for chunk in chunks)


def test_chunk_markdown_falls_back_to_hard_cuts_without_losing_characters():
    text = "A" * 1200

    chunks = chunk_markdown(
        text=text,
        source="docs/no-boundaries.md",
        chunk_overlap=0,
    )

    assert all(len(chunk.content) <= 512 for chunk in chunks)
    assert "".join(chunk.content for chunk in chunks) == text


def test_chunk_markdown_ignores_headings_inside_code_fences():
    chunks = chunk_markdown(
        text=(
            "## 部署\n"
            "```bash\n"
            "# 安装依赖\n"
            "pip install tutor-agent\n"
            "# 启动服务\n"
            "uvicorn app.main:app\n"
            "```\n"
            "部署完成后的尾注。"
        ),
        source="docs/deployment.md",
    )

    assert len(chunks) == 1
    assert chunks[0].title_path == "部署"
    assert chunks[0].content.count("```") == 2


def test_chunk_markdown_rewraps_each_long_code_block_piece():
    code_lines = [f"print('完整代码行 {index:03d}')" for index in range(80)]
    chunks = chunk_markdown(
        text="```python\n" + "\n".join(code_lines) + "\n```",
        source="docs/long-code.md",
    )

    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 512 for chunk in chunks)
    assert all(chunk.content.startswith("```python\n") for chunk in chunks)
    assert all(chunk.content.count("```") == 2 for chunk in chunks)
    assert [
        line
        for chunk in chunks
        for line in chunk.content.splitlines()[1:-1]
    ] == code_lines


def test_chunk_markdown_repeats_table_header_without_splitting_rows():
    header = ["| 编号 | 技能 |", "| --- | --- |"]
    data_rows = [
        f"| {index:03d} | 完整的数据行内容 {index:03d} |" for index in range(80)
    ]
    chunks = chunk_markdown(
        text="\n".join(header + data_rows),
        source="docs/long-table.md",
    )

    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 512 for chunk in chunks)
    assert all(chunk.content.splitlines()[:2] == header for chunk in chunks)
    emitted_rows = [
        line
        for chunk in chunks
        for line in chunk.content.splitlines()[2:]
    ]
    assert emitted_rows == data_rows
    assert all(row.endswith("|") for row in emitted_rows)


def test_chunk_markdown_repeats_list_intro_without_splitting_items():
    intro = "以下是必备技能:"
    items = [
        f"- 第{index:03d}项技能：理解并实践完整的后端开发步骤。"
        for index in range(50)
    ]
    chunks = chunk_markdown(
        text=intro + "\n" + "\n".join(items),
        source="docs/long-list.md",
    )

    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 512 for chunk in chunks)
    assert all(chunk.content.splitlines()[0] == intro for chunk in chunks)
    emitted_items = [
        line
        for chunk in chunks
        for line in chunk.content.splitlines()[1:]
    ]
    assert emitted_items == items
    assert all(item.startswith("- ") and item.endswith("。") for item in emitted_items)
