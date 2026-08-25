"""Tests for PDF-to-pseudo-Markdown conversion."""

import pytest

from app.services.documents.parsed_document import ParsedDocument, ParsedPage, ParsedTextBlock
from app.services.documents.pdf_markdown_converter import (
    parsed_pdf_to_markdown,
    strip_page_sentinels,
)
from app.services.knowledge_chunker import chunk_markdown


def make_block(index: int, text: str, *, height: float = 10.0, top: float = 0.0):
    return ParsedTextBlock(index, text, (0.0, top, 100.0, top + height))


def make_document(page_blocks: list[list[ParsedTextBlock]], filename: str = "机器学习导论.pdf"):
    pages = tuple(
        ParsedPage(
            page_number=index,
            width=600.0,
            height=800.0,
            blocks=tuple(blocks),
        )
        for index, blocks in enumerate(page_blocks, start=1)
    )
    return ParsedDocument(
        schema_version=2,
        document_id="doc-1",
        original_filename=filename,
        page_count=len(pages),
        extracted_char_count=sum(
            len(block.text.replace(" ", ""))
            for blocks in page_blocks
            for block in blocks
        ),
        pages=pages,
    )


def test_repeated_header_footer_removed_only_when_seen_on_more_than_sixty_percent_pages():
    pages = []
    for index in range(1, 6):
        blocks = [
            make_block(0, f"Tutor Agent {index}"),
            make_block(1, f"正文第 {index} 页。"),
        ]
        if index <= 4:
            blocks.append(make_block(2, "版权所有 2026"))
        pages.append(blocks)

    markdown = parsed_pdf_to_markdown(make_document(pages))

    assert "Tutor Agent" not in markdown
    assert "版权所有" not in markdown

    kept_pages = [
        [make_block(0, "只出现两次"), make_block(1, "正文。")]
        if index in {1, 2}
        else [make_block(0, "正文。")]
        for index in range(1, 6)
    ]
    assert "只出现两次" in parsed_pdf_to_markdown(make_document(kept_pages))


def test_two_page_document_skips_repeated_header_filter_but_removes_page_numbers():
    pages = [
        [make_block(0, "重复页眉"), make_block(1, "1"), make_block(2, "正文一。")],
        [make_block(0, "重复页眉"), make_block(1, "2"), make_block(2, "正文二。")],
    ]

    markdown = parsed_pdf_to_markdown(make_document(pages))

    assert markdown.count("重复页眉") == 2
    assert "正文一。" in markdown and "正文二。" in markdown


def test_unfinished_page_tail_and_next_page_head_are_continuous_after_sentinel_strip():
    document = make_document(
        [
            [make_block(0, "这是一个未完的句子")],
            [make_block(0, "下一页继续完成。")],
        ]
    )

    markdown = parsed_pdf_to_markdown(document)
    body, _, _ = strip_page_sentinels(markdown)

    assert "这是一个未完的句子下一页继续完成。" in body
    assert "未完的句子\n" not in body


def test_sentence_ending_page_tail_is_not_merged():
    document = make_document(
        [
            [make_block(0, "这一页已经结束。")],
            [make_block(0, "下一页的新段落。")],
        ]
    )

    body, _, _ = strip_page_sentinels(parsed_pdf_to_markdown(document))

    assert "这一页已经结束。\n\n下一页的新段落。" in body


def test_numbered_and_large_blocks_are_rendered_as_headings():
    document = make_document(
        [
            [
                make_block(0, "第 1 章 绪论"),
                make_block(1, "1.1 监督学习"),
                make_block(2, "突出显示的标题", height=30.0),
                make_block(3, "正文内容。", height=10.0),
            ]
        ]
    )

    markdown = parsed_pdf_to_markdown(document)

    assert "## 第 1 章 绪论" in markdown
    assert "### 1.1 监督学习" in markdown
    assert "## 突出显示的标题" in markdown
    assert "# 机器学习导论.pdf" in markdown


def test_strip_page_sentinels_single_page_cross_page_and_missing():
    assert strip_page_sentinels("<!--page:3-->\n正文") == ("正文", 3, 3)
    assert strip_page_sentinels("<!--page:2-->\n甲\n<!--page:4-->\n乙") == (
        "甲\n乙",
        2,
        4,
    )
    original = "没有页码哨兵"
    assert strip_page_sentinels(original) == (original, None, None)


def test_chunks_keep_page_sentinels_and_allow_previous_page_fallback():
    pages = [
        [make_block(0, "第一页内容。" + "甲" * 700)],
        [make_block(0, "第二页内容。" + "乙" * 700)],
    ]
    markdown = parsed_pdf_to_markdown(make_document(pages))
    chunks = chunk_markdown(markdown, source="x.pdf")

    previous_page_end = None
    for chunk in chunks:
        _, page_start, page_end = strip_page_sentinels(chunk.content)
        if page_start is None:
            assert previous_page_end is not None
            page_start = page_end = previous_page_end
        assert page_start is not None and page_end is not None
        previous_page_end = page_end


@pytest.mark.parametrize("text", ["DVD", "LCD", "mix", "civil", "vivid", "did"])
def test_roman_numeral_lookalike_words_are_kept(text):
    markdown = parsed_pdf_to_markdown(
        make_document([[make_block(0, text), make_block(1, "正文。")]])
    )

    assert text in markdown


@pytest.mark.parametrize("text", ["1", "12", "iv", "XIV", "３"])
def test_standalone_page_numbers_are_removed(text):
    markdown = parsed_pdf_to_markdown(
        make_document([[make_block(0, text), make_block(1, "正文。")]])
    )
    body, _, _ = strip_page_sentinels(markdown)

    assert text not in body


def test_empty_page_emits_no_sentinel():
    pages = [
        [make_block(0, "重复页眉"), make_block(1, "第一页正文。")],
        [make_block(0, "重复页眉")],
        [make_block(0, "重复页眉")],
        [make_block(0, "重复页眉"), make_block(1, "第四页正文。")],
    ]

    markdown = parsed_pdf_to_markdown(make_document(pages))

    assert "<!--page:1-->" in markdown
    assert "<!--page:4-->" in markdown
    assert "<!--page:2-->" not in markdown
    assert "<!--page:3-->" not in markdown


def test_sentinel_is_placed_after_leading_headings():
    document = make_document(
        [
            [make_block(0, "第一页正文。")],
            [make_block(0, "第 2 章 概述"), make_block(1, "第二页正文。")],
        ]
    )

    markdown = parsed_pdf_to_markdown(document)

    assert markdown.index("## 第 2 章 概述") < markdown.index("<!--page:2-->")


def test_cross_page_continuation_is_seamless_after_strip():
    document = make_document(
        [
            [make_block(0, "这是一个未完的句子")],
            [make_block(0, "下一页继续完成。")],
        ]
    )

    body, _, _ = strip_page_sentinels(parsed_pdf_to_markdown(document))

    assert "这是一个未完的句子下一页继续完成。" in body
    assert "未完的句子\n" not in body


def test_chunk_page_attribution_is_exact():
    document = make_document(
        [
            [make_block(0, "甲" * 700)],
            [make_block(0, "第 2 章 乙章"), make_block(1, "乙" * 700)],
            [make_block(0, "丙" * 700)],
        ]
    )
    chunks = chunk_markdown(
        parsed_pdf_to_markdown(document),
        source="x.pdf",
    )

    previous_page_end = None
    chunk_pages = []
    for chunk in chunks:
        body, page_start, page_end = strip_page_sentinels(chunk.content)
        if page_start is None:
            page_start = page_end = previous_page_end
        assert page_start is not None and page_end is not None
        previous_page_end = page_end
        chunk_pages.append((body, page_start, page_end))

    assert all(
        page_start == page_end == 1
        for body, page_start, page_end in chunk_pages
        if "甲" * 10 in body
    )
    assert all(
        page_start == page_end == 2
        for body, page_start, page_end in chunk_pages
        if "乙" * 10 in body
    )
    assert all(
        page_start == page_end == 3
        for body, page_start, page_end in chunk_pages
        if "丙" * 10 in body
    )
    assert not any(
        "甲" * 10 in body and page_end >= 2
        for body, _, page_end in chunk_pages
    )
