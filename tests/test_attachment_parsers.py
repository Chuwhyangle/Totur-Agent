from pathlib import Path

import pytest

from app.services.documents.attachment_parsers import AttachmentParserDispatch


def parse_file(tmp_path: Path, filename: str, content: str):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return AttachmentParserDispatch().parse(
        path,
        document_id="doc-1",
        original_filename=filename,
        max_pages=20,
        min_extracted_chars=1,
    )


@pytest.mark.parametrize(
    ("filename", "content_kind", "locator_unit"),
    [
        ("notes.txt", "text", "line"),
        ("script.py", "code", "line"),
        ("table.csv", "csv", "row"),
        ("data.json", "json", "section"),
        ("page.html", "html", "section"),
    ],
)
def test_dispatch_parses_textual_attachment_kinds(
    tmp_path,
    filename,
    content_kind,
    locator_unit,
):
    content = {
        "notes.txt": "one\ntwo\n",
        "script.py": "print('ok')\n",
        "table.csv": "name,value\nalpha,1\n",
        "data.json": '{"answer": 42}',
        "page.html": "<html><h1>Title</h1><p>Body</p></html>",
    }[filename]

    parsed = parse_file(tmp_path, filename, content)

    assert parsed.content_kind == content_kind
    assert parsed.locator_unit == locator_unit
    assert parsed.page_count == len(parsed.pages) > 0
    assert parsed.extracted_char_count > 0
    assert all(page.width == 0.0 and page.height == 0.0 for page in parsed.pages)
    assert all(block.bbox == (0.0, 0.0, 0.0, 0.0) for page in parsed.pages for block in page.blocks)


def test_text_is_split_into_120_line_virtual_pages(tmp_path):
    parsed = parse_file(
        tmp_path,
        "notes.txt",
        "\n".join(f"line {index}" for index in range(1, 241)),
    )

    assert parsed.page_count == 2
    assert (parsed.pages[0].locator_start, parsed.pages[0].locator_end) == (1, 120)
    assert (parsed.pages[1].locator_start, parsed.pages[1].locator_end) == (121, 240)


def test_markdown_heading_sections_get_section_locators(tmp_path):
    parsed = parse_file(
        tmp_path,
        "notes.md",
        "# Intro\nfirst\n## Details\nsecond\n",
    )

    assert parsed.content_kind == "markdown"
    assert parsed.locator_unit == "section"
    assert parsed.page_count == 2
    assert [page.locator for page in parsed.pages] == ["Intro", "Details"]


def test_parser_identity_is_extension_aware():
    dispatch = AttachmentParserDispatch()

    assert dispatch.identity_for("notes.pdf")[0] == "pymupdf"
    assert dispatch.identity_for("notes.md") == ("markdown", "1")
    assert dispatch.identity_for("notes.txt") == ("text", "1")
