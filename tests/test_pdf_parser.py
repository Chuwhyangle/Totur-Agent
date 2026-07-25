"""Tests for real PDF validation and ordered Page/Block extraction."""

from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

import app.services.documents.pdf_parser as pdf_parser_module
from app.services.documents.pdf_parser import (
    EncryptedPdfNotSupported,
    InvalidPdfError,
    NoExtractableText,
    PdfContentLimitExceeded,
    PdfPageLimitExceeded,
    PdfParseFailed,
    PdfParser,
    PdfSourceUnavailable,
)


def create_text_pdf(path: Path, pages: list[list[tuple[float, str]]]) -> Path:
    document = pymupdf.open()
    try:
        for entries in pages:
            page = document.new_page()
            for y_position, text in entries:
                page.insert_text((72, y_position), text)
        document.save(path)
    finally:
        document.close()
    return path


def create_encrypted_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "secret protected text")
        document.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    finally:
        document.close()
    return path


def create_image_only_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page()
        pixmap = pymupdf.Pixmap(
            pymupdf.csRGB,
            pymupdf.IRect(0, 0, 10, 10),
            False,
        )
        pixmap.clear_with(255)
        page.insert_image(page.rect, pixmap=pixmap)
        document.save(path)
    finally:
        document.close()
    return path


def parse(
    path: Path,
    *,
    max_pages: int = 10,
    min_chars: int = 3,
    max_chars: int = 2_000_000,
    max_blocks_per_page: int = 5_000,
):
    return PdfParser().parse(
        source_path=path,
        document_id="document-123",
        original_filename="paper.pdf",
        max_pages=max_pages,
        min_extracted_chars=min_chars,
        max_extracted_chars=max_chars,
        max_blocks_per_page=max_blocks_per_page,
    )


def test_single_page_text_pdf_parses_to_stable_model(tmp_path):
    path = create_text_pdf(
        tmp_path / "single.pdf",
        [[(72, "Hello from a real PDF text layer")]],
    )

    result = parse(path)

    assert result.schema_version == 1
    assert result.document_id == "document-123"
    assert result.original_filename == "paper.pdf"
    assert result.page_count == 1
    assert result.pages[0].page_number == 1
    assert result.pages[0].blocks[0].text == "Hello from a real PDF text layer"


def test_multi_page_pdf_preserves_one_based_page_order(tmp_path):
    path = create_text_pdf(
        tmp_path / "multi.pdf",
        [
            [(72, "First page content")],
            [(72, "Second page content")],
            [(72, "Third page content")],
        ],
    )

    result = parse(path)

    assert [page.page_number for page in result.pages] == [1, 2, 3]
    assert [page.blocks[0].text for page in result.pages] == [
        "First page content",
        "Second page content",
        "Third page content",
    ]


def test_multiple_blocks_follow_visual_order_and_have_float_bbox(tmp_path):
    path = create_text_pdf(
        tmp_path / "blocks.pdf",
        [[(220, "Lower block"), (72, "Upper block")]],
    )

    payload = parse(path).to_dict()
    blocks = payload["pages"][0]["blocks"]

    assert [block["block_index"] for block in blocks] == [0, 1]
    assert [block["text"] for block in blocks] == [
        "Upper block",
        "Lower block",
    ]
    assert all(isinstance(value, float) for value in blocks[0]["bbox"])


class FakePage:
    def __init__(self, blocks):
        self.blocks = blocks
        self.rect = SimpleNamespace(width=595, height=842)

    def get_text(self, mode, *, sort):
        assert mode == "blocks"
        assert sort is True
        return self.blocks


class FakeDocument:
    is_pdf = True
    needs_pass = False
    is_encrypted = False

    def __init__(self, blocks=None, *, fail=False):
        self.page_count = 1
        self.page = FakePage(blocks or [])
        self.fail = fail
        self.closed = False

    def load_page(self, page_index):
        assert page_index == 0
        if self.fail:
            raise RuntimeError("page extraction failed")
        return self.page

    def close(self):
        self.closed = True


def test_blank_blocks_are_filtered_and_chinese_text_is_preserved(monkeypatch):
    document = FakeDocument(
        [
            (0, 0, 10, 10, "  \n\n", 0, 0),
            (1, 2, 20, 30, "  中文解析内容  \n", 1, 0),
            (2, 3, 20, 30, "ignored image", 2, 1),
        ]
    )
    monkeypatch.setattr(pdf_parser_module.pymupdf, "open", lambda _path: document)

    result = parse(Path("unused.pdf"), min_chars=1)

    assert [block.text for block in result.pages[0].blocks] == [
        "中文解析内容"
    ]
    assert result.pages[0].blocks[0].block_index == 0


def test_corrupt_pdf_is_classified_as_invalid(tmp_path):
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-not-a-real-document")

    with pytest.raises(InvalidPdfError) as error:
        parse(path)

    assert error.value.error_code == "INVALID_PDF"


def test_encrypted_pdf_is_rejected_with_stable_code(tmp_path):
    path = create_encrypted_pdf(tmp_path / "encrypted.pdf")

    with pytest.raises(EncryptedPdfNotSupported) as error:
        parse(path)

    assert error.value.error_code == "ENCRYPTED_PDF_NOT_SUPPORTED"


def test_page_limit_is_enforced_before_text_extraction(tmp_path):
    path = create_text_pdf(
        tmp_path / "too-many.pdf",
        [[(72, "one")], [(72, "two")], [(72, "three")]],
    )

    with pytest.raises(PdfPageLimitExceeded) as error:
        parse(path, max_pages=2, min_chars=1)

    assert error.value.error_code == "PDF_PAGE_LIMIT_EXCEEDED"


def test_blank_pdf_has_no_extractable_text(tmp_path):
    document = pymupdf.open()
    path = tmp_path / "blank.pdf"
    try:
        document.new_page()
        document.save(path)
    finally:
        document.close()

    with pytest.raises(NoExtractableText) as error:
        parse(path, min_chars=1)

    assert error.value.error_code == "NO_EXTRACTABLE_TEXT"


def test_image_only_pdf_has_no_extractable_text(tmp_path):
    path = create_image_only_pdf(tmp_path / "image-only.pdf")

    with pytest.raises(NoExtractableText):
        parse(path, min_chars=1)


def test_blank_pages_are_allowed_when_document_has_enough_text(tmp_path):
    path = create_text_pdf(
        tmp_path / "mixed.pdf",
        [[], [(72, "This second page has extractable text")], []],
    )

    result = parse(path, min_chars=5)

    assert result.page_count == 3
    assert result.pages[0].blocks == ()
    assert result.pages[1].blocks[0].text.startswith("This second page")
    assert result.pages[2].blocks == ()


def test_unexpected_extraction_failure_is_stable_and_document_closes(monkeypatch):
    document = FakeDocument(fail=True)
    monkeypatch.setattr(pdf_parser_module.pymupdf, "open", lambda _path: document)

    with pytest.raises(PdfParseFailed) as error:
        parse(Path("unused.pdf"), min_chars=1)

    assert error.value.error_code == "PDF_PARSE_FAILED"
    assert document.closed is True


def test_missing_source_is_classified_as_unavailable(tmp_path):
    with pytest.raises(PdfSourceUnavailable) as error:
        parse(tmp_path / "missing.pdf")

    assert error.value.error_code == "PDF_SOURCE_UNAVAILABLE"


def test_extracted_character_limit_stops_parsing(tmp_path):
    path = create_text_pdf(
        tmp_path / "too-much-text.pdf",
        [[(72, "abcdefghij")]],
    )

    with pytest.raises(PdfContentLimitExceeded) as error:
        parse(path, min_chars=1, max_chars=5)

    assert error.value.error_code == "PDF_CONTENT_LIMIT_EXCEEDED"


def test_per_page_block_limit_stops_parsing(monkeypatch):
    document = FakeDocument(
        [
            (0, 0, 10, 10, "first", 0, 0),
            (0, 20, 10, 30, "second", 1, 0),
        ]
    )
    monkeypatch.setattr(pdf_parser_module.pymupdf, "open", lambda _path: document)

    with pytest.raises(PdfContentLimitExceeded) as error:
        parse(Path("unused.pdf"), min_chars=1, max_blocks_per_page=1)

    assert error.value.error_code == "PDF_CONTENT_LIMIT_EXCEEDED"
    assert document.closed is True
