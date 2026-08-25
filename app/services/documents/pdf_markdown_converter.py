"""Convert parsed PDF blocks into heading-aware pseudo Markdown."""

from __future__ import annotations

from collections import defaultdict
import re
from statistics import median

from app.services.documents.parsed_document import ParsedDocument, ParsedPage, ParsedTextBlock


_PAGE_SENTINEL_PATTERN = re.compile(r"<!--page:(\d+)-->")
_PAGE_SENTINEL_LINE_PATTERN = re.compile(
    r"^[ \t]*<!--page:\d+-->[ \t]*(?:\r?\n|$)",
    re.MULTILINE,
)
_ROMAN_OR_DIGITS_PATTERN = re.compile(r"[0-9\uff10-\uff19IVXLCDMivxlcdm]+")
_CHAPTER_HEADING_PATTERN = re.compile(r"^第\s*\d+\s*章")
_CHAPTER_ENGLISH_PATTERN = re.compile(r"^Chapter\s+\d+\b", re.IGNORECASE)
_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(\d+(?:[.\uff0e]\d+){0,2})(?:[.\uff0e)]|\s|$)"
)
_SENTENCE_ENDINGS = frozenset("。．…！？；.!?;")
_CLOSING_CHARACTERS = frozenset(
    "\u3009\u300d\u300f\u201d\u2019\"')\uff09\u3011\u300b]"
)


def parsed_pdf_to_markdown(document: ParsedDocument) -> str:
    """Render a parsed PDF as pseudo Markdown with one page sentinel per page."""

    pages = _remove_repeated_headers_and_footers(document.pages, document.page_count)
    merged_page_numbers = _find_cross_page_continuations(pages)

    output = f"# {document.original_filename}\n\n"
    for page_index, (page, blocks) in enumerate(zip(document.pages, pages)):
        page_number = page.page_number
        if page_index:
            separator = "\n" if page_number in merged_page_numbers else "\n\n"
            output += separator
        output += f"<!--page:{page_number}-->"

        if blocks:
            page_median = _median_block_height(blocks)
            rendered = [
                _render_block(block, page_median)
                for block in blocks
                if block.text.strip()
            ]
            if rendered:
                output += "\n\n" if page_index == 0 else "\n"
                output += "\n\n".join(rendered)

    return output.rstrip() + "\n"


def strip_page_sentinels(text: str) -> tuple[str, int | None, int | None]:
    """Remove page sentinels and return the smallest and largest page numbers.

    If no sentinel is present, ``(text, None, None)`` is returned. Callers
    should then carry forward the previous chunk's page end as a fallback.
    """

    page_numbers = [
        int(match.group(1)) for match in _PAGE_SENTINEL_PATTERN.finditer(text)
    ]
    if not page_numbers:
        return text, None, None

    cleaned = _PAGE_SENTINEL_LINE_PATTERN.sub("", text)
    cleaned = _PAGE_SENTINEL_PATTERN.sub("", cleaned)
    return cleaned, min(page_numbers), max(page_numbers)


def _remove_repeated_headers_and_footers(
    pages: tuple[ParsedPage, ...],
    page_count: int,
) -> list[list[ParsedTextBlock]]:
    """Apply page-number and cross-page repetition filters to page blocks."""

    page_blocks = [
        [block for block in page.blocks if not _is_standalone_page_number(block.text)]
        for page in pages
    ]
    if page_count < 3:
        return page_blocks

    occurrences: dict[str, set[int]] = defaultdict(set)
    for page_index, blocks in enumerate(page_blocks):
        for block in blocks:
            key = _header_footer_key(block.text)
            if key and len(block.text.strip()) < 80:
                occurrences[key].add(page_index)

    repeated_keys = {
        key
        for key, page_indexes in occurrences.items()
        if len(page_indexes) > page_count * 0.6
    }
    if not repeated_keys:
        return page_blocks

    return [
        [block for block in blocks if _header_footer_key(block.text) not in repeated_keys]
        for blocks in page_blocks
    ]


def _header_footer_key(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    return re.sub(r"\d", "", compact)


def _is_standalone_page_number(text: str) -> bool:
    stripped = text.strip()
    return (
        0 < len(stripped) < 10
        and _ROMAN_OR_DIGITS_PATTERN.fullmatch(stripped) is not None
    )


def _find_cross_page_continuations(
    pages: list[list[ParsedTextBlock]],
) -> set[int]:
    """Return page numbers whose first block continues the preceding page."""

    merged_page_numbers: set[int] = set()
    for page_index in range(1, len(pages)):
        previous_blocks = pages[page_index - 1]
        current_blocks = pages[page_index]
        if not previous_blocks or not current_blocks:
            continue

        previous = previous_blocks[-1]
        current = current_blocks[0]
        if _ends_with_sentence(previous.text):
            continue
        if _is_title_candidate(current, _median_block_height(current_blocks)):
            continue
        merged_page_numbers.add(page_index + 1)

    return merged_page_numbers


def _median_block_height(blocks: list[ParsedTextBlock]) -> float:
    if not blocks:
        return 0.0
    return float(median(_block_height(block) for block in blocks))


def _block_height(block: ParsedTextBlock) -> float:
    return block.bbox[3] - block.bbox[1]


def _is_title_candidate(block: ParsedTextBlock, page_median: float) -> bool:
    text = block.text.strip()
    if not text or "\n" in text or len(text) >= 60:
        return False
    if _ends_with_sentence(text):
        return False
    if _heading_number_depth(text) is not None:
        return True
    return page_median > 0 and _block_height(block) > page_median * 1.3


def _heading_number_depth(text: str) -> int | None:
    if _CHAPTER_HEADING_PATTERN.match(text) or _CHAPTER_ENGLISH_PATTERN.match(text):
        return 1

    match = _NUMBERED_HEADING_PATTERN.match(text)
    if match is None:
        return None
    return len(re.split(r"[.\uff0e]", match.group(1)))


def _render_block(block: ParsedTextBlock, page_median: float) -> str:
    text = block.text.strip()
    if not _is_title_candidate(block, page_median):
        return text

    depth = _heading_number_depth(text)
    level = 2 if depth is None or depth <= 1 else 3
    return f"{'#' * level} {text}"


def _ends_with_sentence(text: str) -> bool:
    stripped = text.rstrip()
    while stripped and stripped[-1] in _CLOSING_CHARACTERS:
        stripped = stripped[:-1].rstrip()
    return bool(stripped) and stripped[-1] in _SENTENCE_ENDINGS
