"""Markdown chunking for learning-note knowledge bases."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.rag_settings import CHUNK_OVERLAP, CHUNK_SIZE, subject_from_source


HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
FENCE_OPEN_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$"
)
LIST_ITEM_PATTERN = re.compile(
    r"^\s*(?:[-*+]|\d{1,3}[.\u3001\uff0e)])\s+"
)
TOP_LEVEL_LIST_ITEM_PATTERN = re.compile(
    r"^(?:[-*+]|\d{1,3}[.\u3001\uff0e)])\s+"
)
PARAGRAPH_BREAK_PATTERN = re.compile(r"\n[ \t]*\n")
TITLE_PATH_SEPARATOR = " > "
DIRECT_SENTENCE_ENDINGS = frozenset("\u3002\u2026\uff01\uff1f\uff1b")
ASCII_SENTENCE_ENDINGS = frozenset("!?;.")
CLOSING_CHARACTERS = frozenset(
    "\u300d\u300f\u201d\u2019\"')\uff09]\u3011\u300b"
)
SOFT_BOUNDARIES = frozenset(",\uff0c\u3001 \t")


@dataclass(frozen=True)
class KnowledgeChunk:
    """A deterministic learning-note chunk ready for vector indexing."""

    content: str
    source: str
    title_path: str
    chunk_index: int
    subject: str = "general"

    @property
    def chunk_id(self) -> str:
        """Return the stable chunk identifier used by index consumers."""

        return f"{self.source}#{self.chunk_index}"


@dataclass(frozen=True)
class _Block:
    kind: str
    text: str
    intro: str = ""


def chunk_markdown(
    text: str,
    source: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    subject: str | None = None,
) -> list[KnowledgeChunk]:
    """Split Markdown into heading-aware ``KnowledgeChunk`` objects."""

    _validate_window(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks: list[KnowledgeChunk] = []
    title_stack: list[str] = []
    section_lines: list[str] = []
    section_title_path = ""
    open_fence: tuple[str, int] | None = None

    def flush_section() -> None:
        nonlocal section_lines, section_title_path

        chunks.extend(
            _chunks_from_section(
                lines=section_lines,
                source=source,
                title_path=section_title_path,
                start_index=len(chunks),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                subject=subject or subject_from_source(source),
            )
        )
        section_lines = []

    for line in text.splitlines():
        if open_fence is not None:
            section_lines.append(line)
            if _is_closing_fence(line, *open_fence):
                open_fence = None
            continue

        fence = _fence_marker(line)
        if fence is not None:
            section_lines.append(line)
            open_fence = fence
            continue

        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            flush_section()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            title_stack = title_stack[: level - 1]
            title_stack.append(title)
            section_title_path = TITLE_PATH_SEPARATOR.join(title_stack)
            section_lines = [line.strip()]
            continue

        section_lines.append(line.rstrip())

    flush_section()
    return chunks


def _fence_marker(line: str) -> tuple[str, int] | None:
    match = FENCE_OPEN_PATTERN.match(line)
    if match is None:
        return None

    marker = match.group(1)
    return marker[0], len(marker)


def _is_closing_fence(line: str, marker: str, minimum_length: int) -> bool:
    stripped = line.strip()
    return (
        len(stripped) >= minimum_length
        and bool(stripped)
        and all(character == marker for character in stripped)
    )


def _chunks_from_section(
    lines: list[str],
    source: str,
    title_path: str,
    start_index: int,
    chunk_size: int,
    chunk_overlap: int,
    subject: str,
) -> list[KnowledgeChunk]:
    """Convert one heading section into one or more chunks."""

    if not lines:
        return []

    content = "\n".join(lines).strip()
    if not content:
        return []

    if title_path and _section_body(lines) == "":
        return []

    pieces = _split_section_content(
        lines=lines,
        content=content,
        title_path=title_path,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return [
        KnowledgeChunk(
            content=piece,
            source=source,
            title_path=title_path,
            chunk_index=start_index + index,
            subject=subject,
        )
        for index, piece in enumerate(pieces)
    ]


def _section_body(lines: list[str]) -> str:
    """Return section text without its leading ATX heading."""

    if lines and HEADING_PATTERN.match(lines[0]):
        return "\n".join(lines[1:]).strip()

    return "\n".join(lines).strip()


def _split_section_content(
    lines: list[str],
    content: str,
    title_path: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Split a section while preserving the existing heading prefix behavior."""

    if len(content) <= chunk_size:
        return [content]

    if not title_path or not HEADING_PATTERN.match(lines[0]):
        return _split_blockwise(
            content=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    title_line = lines[0].strip()
    body = _section_body(lines)
    body_chunk_size = chunk_size - len(title_line) - 1
    if body_chunk_size <= 0:
        return _split_with_overlap(
            content=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    body_overlap = min(chunk_overlap, max(0, body_chunk_size - 1))
    body_pieces = _split_blockwise(
        content=body,
        chunk_size=body_chunk_size,
        chunk_overlap=body_overlap,
    )

    return [f"{title_line}\n{piece}".strip() for piece in body_pieces]


def _parse_blocks(content: str) -> list[_Block]:
    lines = content.splitlines()
    blocks: list[_Block] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _fence_marker(line)
        if fence is not None:
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_line = lines[index]
                code_lines.append(code_line)
                index += 1
                if _is_closing_fence(code_line, *fence):
                    break
            blocks.append(_Block(kind="code", text="\n".join(code_lines)))
            continue

        if TABLE_ROW_PATTERN.match(line):
            table_lines: list[str] = []
            while index < len(lines) and TABLE_ROW_PATTERN.match(lines[index]):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_Block(kind="table", text="\n".join(table_lines)))
            continue

        if LIST_ITEM_PATTERN.match(line):
            intro = _take_list_intro(blocks, lines, index)
            list_lines: list[str] = []
            while index < len(lines):
                list_line = lines[index]
                if LIST_ITEM_PATTERN.match(list_line):
                    list_lines.append(list_line)
                    index += 1
                    continue
                if not list_line.strip():
                    if (
                        index + 1 < len(lines)
                        and LIST_ITEM_PATTERN.match(lines[index + 1])
                    ):
                        list_lines.append(list_line)
                        index += 1
                        continue
                    break
                if list_line.startswith((" ", "\t")):
                    list_lines.append(list_line)
                    index += 1
                    continue
                break
            blocks.append(
                _Block(kind="list", text="\n".join(list_lines), intro=intro)
            )
            continue

        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            candidate = lines[index]
            if text_lines and _starts_structural_block(candidate):
                break
            text_lines.append(candidate.rstrip())
            index += 1
        text = "\n".join(text_lines).strip()
        if text:
            blocks.append(_Block(kind="text", text=text))

    return blocks


def _starts_structural_block(line: str) -> bool:
    return bool(
        _fence_marker(line)
        or TABLE_ROW_PATTERN.match(line)
        or LIST_ITEM_PATTERN.match(line)
    )


def _take_list_intro(blocks: list[_Block], lines: list[str], index: int) -> str:
    if index == 0 or not blocks or blocks[-1].kind != "text":
        return ""

    source_line = lines[index - 1]
    candidate = source_line.strip()
    if (
        not candidate
        or len(candidate) > 80
        or not candidate.endswith((":", "\uff1a"))
    ):
        return ""

    previous_lines = blocks[-1].text.splitlines()
    if not previous_lines or previous_lines[-1].strip() != candidate:
        return ""

    remaining = "\n".join(previous_lines[:-1]).strip()
    if remaining:
        blocks[-1] = _Block(kind="text", text=remaining)
    else:
        blocks.pop()
    return candidate


def _split_blockwise(
    content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    block_pieces: list[str] = []
    for block in _parse_blocks(content):
        block_pieces.extend(
            _split_block(
                block=block,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    bounded_pieces: list[str] = []
    for piece in block_pieces:
        if len(piece) <= chunk_size:
            bounded_pieces.append(piece)
        else:
            bounded_pieces.extend(
                _split_with_overlap(
                    content=piece,
                    chunk_size=chunk_size,
                    chunk_overlap=0,
                )
            )

    return _pack_pieces(bounded_pieces, chunk_size=chunk_size, separator="\n\n")


def _split_block(
    block: _Block,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    rendered = _render_block(block)
    if len(rendered) <= chunk_size:
        return [rendered]

    if block.kind == "code":
        return _split_code_block(block.text, chunk_size=chunk_size)
    if block.kind == "table":
        return _split_table_block(block.text, chunk_size=chunk_size)
    if block.kind == "list":
        return _split_list_block(
            block,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    return _split_with_overlap(
        content=block.text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def _render_block(block: _Block) -> str:
    if block.intro:
        return f"{block.intro}\n{block.text}"
    return block.text


def _split_code_block(content: str, chunk_size: int) -> list[str]:
    lines = content.splitlines()
    if not lines:
        return []

    opening_line = lines[0].rstrip()
    fence = _fence_marker(opening_line)
    if fence is None:
        return _split_with_overlap(content, chunk_size=chunk_size, chunk_overlap=0)

    is_closed = len(lines) > 1 and _is_closing_fence(lines[-1], *fence)
    closing_line = lines[-1].strip() if is_closed else fence[0] * fence[1]
    body_lines = lines[1:-1] if is_closed else lines[1:]
    body_budget = chunk_size - len(opening_line) - len(closing_line) - 2
    if body_budget <= 0:
        return _split_with_overlap(content, chunk_size=chunk_size, chunk_overlap=0)

    groups = _group_lines_by_budget(body_lines, budget=body_budget) or [""]
    return [f"{opening_line}\n{group}\n{closing_line}" for group in groups]


def _split_table_block(content: str, chunk_size: int) -> list[str]:
    lines = content.splitlines()
    has_header = len(lines) >= 2 and bool(TABLE_SEPARATOR_PATTERN.match(lines[1]))
    if not has_header:
        return _group_lines_by_budget(lines, budget=chunk_size)

    header_lines = lines[:2]
    data_lines = lines[2:]
    header = "\n".join(header_lines)
    data_budget = chunk_size - len(header) - 1
    if data_budget <= 0 or not data_lines:
        return _split_with_overlap(content, chunk_size=chunk_size, chunk_overlap=0)

    groups = _group_lines_by_budget(data_lines, budget=data_budget)
    return [f"{header}\n{group}" for group in groups]


def _split_list_block(
    block: _Block,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    prefix = f"{block.intro}\n" if block.intro else ""
    item_budget = chunk_size - len(prefix)
    if item_budget <= 0:
        return _split_with_overlap(
            _render_block(block),
            chunk_size=chunk_size,
            chunk_overlap=0,
        )

    item_pieces: list[str] = []
    item_overlap = min(chunk_overlap, max(0, item_budget - 1))
    for item in _split_top_level_items(block.text):
        if len(item) <= item_budget:
            item_pieces.append(item)
        else:
            item_pieces.extend(
                _split_with_overlap(
                    content=item,
                    chunk_size=item_budget,
                    chunk_overlap=item_overlap,
                )
            )

    grouped_items = _pack_pieces(
        item_pieces,
        chunk_size=item_budget,
        separator="\n",
    )
    return [f"{prefix}{group}".strip("\n") for group in grouped_items]


def _split_top_level_items(content: str) -> list[str]:
    items: list[str] = []
    current_lines: list[str] = []

    for line in content.splitlines():
        if TOP_LEVEL_LIST_ITEM_PATTERN.match(line) and current_lines:
            items.append("\n".join(current_lines).strip("\n"))
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        items.append("\n".join(current_lines).strip("\n"))
    return [item for item in items if item]


def _group_lines_by_budget(lines: list[str], budget: int) -> list[str]:
    if budget <= 0:
        return []

    groups: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    def flush_current() -> None:
        nonlocal current_lines, current_length
        if current_lines:
            groups.append("\n".join(current_lines))
        current_lines = []
        current_length = 0

    for line in lines:
        if len(line) > budget:
            flush_current()
            groups.extend(
                line[offset : offset + budget]
                for offset in range(0, len(line), budget)
            )
            continue

        candidate_length = len(line)
        if current_lines:
            candidate_length += current_length + 1

        if current_lines and candidate_length > budget:
            flush_current()
            current_lines = [line]
            current_length = len(line)
        else:
            current_lines.append(line)
            current_length = candidate_length

    flush_current()
    return groups


def _pack_pieces(
    pieces: list[str],
    chunk_size: int,
    separator: str,
) -> list[str]:
    packed: list[str] = []
    current = ""

    for raw_piece in pieces:
        piece = raw_piece.strip("\n")
        if not piece.strip():
            continue

        candidate = piece if not current else f"{current}{separator}{piece}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            packed.append(current)
        current = piece

    if current:
        packed.append(current)
    return packed


def _split_with_overlap(
    content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Split text at semantic boundaries while retaining aligned overlap."""

    if len(content) <= chunk_size:
        return [content]

    pieces: list[str] = []
    start = 0
    min_advance = max(chunk_size // 2, chunk_overlap + 1)

    while start < len(content):
        hard_end = min(start + chunk_size, len(content))
        if hard_end >= len(content):
            piece = content[start:].strip()
            if piece:
                pieces.append(piece)
            break

        minimum_cut = min(start + min_advance, hard_end)
        cut = _find_semantic_cut(
            content=content,
            start=start,
            hard_end=hard_end,
            minimum_cut=minimum_cut,
        )
        piece = content[start:cut].strip()
        if piece:
            pieces.append(piece)

        if chunk_overlap == 0:
            start = cut
        else:
            target = cut - chunk_overlap
            start = _align_overlap_start(
                content=content,
                current_start=start,
                target=target,
                cut=cut,
                chunk_overlap=chunk_overlap,
            )

    return pieces


def _find_semantic_cut(
    content: str,
    start: int,
    hard_end: int,
    minimum_cut: int,
) -> int:
    paragraph_cut = None
    for match in PARAGRAPH_BREAK_PATTERN.finditer(content, start, hard_end):
        if match.end() >= minimum_cut:
            paragraph_cut = match.end()
    if paragraph_cut is not None:
        return paragraph_cut

    for index in range(hard_end - 1, minimum_cut - 2, -1):
        sentence_end = _sentence_boundary_end(content, index)
        if sentence_end is not None and sentence_end <= hard_end:
            return sentence_end

    newline_index = content.rfind("\n", minimum_cut - 1, hard_end)
    if newline_index != -1:
        return newline_index + 1

    for index in range(hard_end - 1, minimum_cut - 2, -1):
        if content[index] in SOFT_BOUNDARIES:
            return index + 1

    return hard_end


def _sentence_boundary_end(content: str, index: int) -> int | None:
    character = content[index]
    if character not in DIRECT_SENTENCE_ENDINGS | ASCII_SENTENCE_ENDINGS:
        return None

    end = index + 1
    while end < len(content) and content[end] in CLOSING_CHARACTERS:
        end += 1

    if character in ASCII_SENTENCE_ENDINGS:
        if character == "." and index > 0 and content[index - 1].isdigit():
            return None
        if end < len(content) and not content[end].isspace():
            return None

    return end


def _align_overlap_start(
    content: str,
    current_start: int,
    target: int,
    cut: int,
    chunk_overlap: int,
) -> int:
    lower_bound = max(current_start + 1, target - 2 * chunk_overlap)
    candidates: list[int] = []

    newline_index = content.rfind("\n", lower_bound - 1, target)
    if newline_index != -1:
        candidates.append(newline_index + 1)

    for index in range(target - 1, lower_bound - 2, -1):
        sentence_end = _sentence_boundary_end(content, index)
        if sentence_end is not None and sentence_end <= target:
            candidates.append(sentence_end)
            break

    if not candidates:
        return target

    aligned = max(candidates)
    while aligned < cut and content[aligned].isspace():
        aligned += 1

    if current_start < aligned < cut:
        return aligned
    return target


def _validate_window(chunk_size: int, chunk_overlap: int) -> None:
    """Validate window settings so every split loop can advance."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")
