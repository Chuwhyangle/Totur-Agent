"""Tests for deterministic page-aware attachment chunking."""

from app.services.documents.attachment_chunker import AttachmentChunker
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)


def block(index, text):
    return ParsedTextBlock(index, text, (0.0, 0.0, 10.0, 10.0))


def document(*pages):
    return ParsedDocument(
        schema_version=1,
        document_id="doc-123",
        original_filename="paper.pdf",
        page_count=len(pages),
        extracted_char_count=sum(
            sum(not char.isspace() for char in item.text)
            for page in pages
            for item in page.blocks
        ),
        pages=tuple(pages),
    )


def test_chunker_is_page_aware_deterministic_and_preserves_order():
    parsed = document(
        ParsedPage(1, 100.0, 100.0, (block(0, "alpha"), block(1, "beta"))),
        ParsedPage(2, 100.0, 100.0, (block(0, "gamma"),)),
    )
    chunker = AttachmentChunker(chunk_chars=12, overlap_chars=2)

    first = chunker.chunk(parsed)
    second = chunker.chunk(parsed)

    assert first == second
    assert [item.chunk_id for item in first] == ["doc-123:0", "doc-123:1"]
    assert [item.text for item in first] == ["alpha\n\nbeta", "gamma"]
    assert [(item.page_start, item.page_end) for item in first] == [(1, 1), (2, 2)]
    assert all(item.original_filename == "paper.pdf" for item in first)


def test_long_block_uses_overlapping_windows_without_crossing_pages():
    parsed = document(
        ParsedPage(1, 100.0, 100.0, (block(0, "abcdefghijklm"),)),
        ParsedPage(2, 100.0, 100.0, (block(0, "second"),)),
    )

    chunks = AttachmentChunker(chunk_chars=10, overlap_chars=2).chunk(parsed)

    assert [item.text for item in chunks] == ["abcdefghij", "ijklm", "second"]
    assert chunks[0].text[-2:] == chunks[1].text[:2]
    assert [(item.page_start, item.page_end) for item in chunks] == [
        (1, 1),
        (1, 1),
        (2, 2),
    ]


def test_empty_pages_and_blank_blocks_do_not_create_chunks():
    parsed = document(
        ParsedPage(1, 100.0, 100.0, ()),
        ParsedPage(2, 100.0, 100.0, (block(0, "   "),)),
        ParsedPage(3, 100.0, 100.0, (block(0, "usable"),)),
    )

    chunks = AttachmentChunker(chunk_chars=20, overlap_chars=3).chunk(parsed)

    assert len(chunks) == 1
    assert chunks[0].text == "usable"
    assert chunks[0].page_start == 3
