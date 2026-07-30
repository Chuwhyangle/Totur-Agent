"""Deterministic HTML parsing primitives for the Agent interview corpus."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePosixPath
import re
from typing import Iterable, Literal

from bs4 import BeautifulSoup, NavigableString, Tag


ChunkType = Literal[
    "course_overview",
    "lesson_overview",
    "section_overview",
    "qa",
    "topic",
    "article",
    "trend",
]

_REMOVE_SELECTORS = (
    "script",
    "style",
    "noscript",
    "svg",
    ".controls",
    ".progress",
    ".navigate-left",
    ".navigate-right",
    ".navigate-up",
    ".navigate-down",
    ".scroll-hint",
    ".mac-header",
    ".mac-dot",
    ".chapter-badge",
    ".card-foot",
    ".play-icon",
)
_BLOCK_CONTAINERS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "footer",
    "header",
    "main",
    "nav",
    "p",
    "section",
}
_QUESTION_PREFIX_RE = re.compile(r"^\s*Q\s*\d+\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_TREND_RE = re.compile(r"最新进展|最新动态|发展趋势|行业趋势|技术趋势|趋势")


@dataclass(frozen=True)
class ContentBlock:
    """One normalized structural block inside a semantic unit."""

    kind: str
    text: str
    items: tuple[str, ...] = ()
    table_header: tuple[str, ...] = ()
    table_rows: tuple[tuple[str, ...], ...] = ()
    language: str | None = None


@dataclass(frozen=True)
class SemanticUnit:
    """A complete pre-split semantic unit."""

    source: str
    course: str
    lesson: str | None
    title_path: tuple[str, ...]
    question: str | None
    chunk_type: ChunkType
    blocks: tuple[ContentBlock, ...]
    slide_start: int | None
    slide_end: int | None
    unit_index: int = 0
    time_tags: tuple[int, ...] = ()

    @property
    def content(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text)

    @property
    def contains_code(self) -> bool:
        return any(block.kind == "code" for block in self.blocks)

    @property
    def parent_key(self) -> str:
        return f"{self.source}#unit-{self.unit_index:03d}"


@dataclass(frozen=True)
class ParsedAgentDocument:
    """Normalized representation of one source HTML file."""

    source: str
    kind: Literal["reveal", "course_map"]
    course_title: str
    lesson_title: str | None
    subtitle: str | None
    section_titles: tuple[str, ...]
    units: tuple[SemanticUnit, ...]


@dataclass
class _DraftUnit:
    section: str | None
    item_title: str | None
    blocks: list[ContentBlock]
    slide_start: int
    slide_end: int


@dataclass
class _SectionGroup:
    title: str | None
    h3_titles: list[str]
    details: list[_DraftUnit]


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+([\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A,.!?;:])", r"\1", normalized)


def _normalize_source(source: str) -> str:
    return PurePosixPath(str(source).replace("\\", "/")).as_posix()


def _visible_text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return _normalize_text(tag.get_text(" ", strip=True))


def _remove_noise(soup: BeautifulSoup) -> None:
    for selector in _REMOVE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()


def _render_list(tag: Tag) -> ContentBlock | None:
    items: list[str] = []
    for item in tag.find_all("li", recursive=False):
        text = _visible_text(item)
        if text:
            items.append(text)
    if not items:
        return None
    ordered = tag.name == "ol"
    lines = [f"{index}. {item}" if ordered else f"- {item}" for index, item in enumerate(items, 1)]
    return ContentBlock(kind="list", text="\n".join(lines), items=tuple(items))


def _markdown_row(cells: Iterable[str]) -> str:
    escaped = [cell.replace("|", "\\|") for cell in cells]
    return "| " + " | ".join(escaped) + " |"


def _render_table(tag: Tag) -> ContentBlock | None:
    rows: list[tuple[str, ...]] = []
    header: tuple[str, ...] = ()
    for row_index, row in enumerate(tag.find_all("tr")):
        cells = tuple(_visible_text(cell) for cell in row.find_all(["th", "td"], recursive=False))
        if not cells or not any(cells):
            continue
        if not header and (row.find("th") is not None or row_index == 0):
            header = cells
        else:
            rows.append(cells)
    if not header and rows:
        header, rows = rows[0], rows[1:]
    if not header:
        return None
    lines = [_markdown_row(header), _markdown_row("---" for _ in header)]
    lines.extend(_markdown_row(row) for row in rows)
    return ContentBlock(
        kind="table",
        text="\n".join(lines),
        table_header=header,
        table_rows=tuple(rows),
    )


def _render_code(tag: Tag) -> ContentBlock | None:
    code = tag.find("code") or tag
    raw = code.get_text("", strip=False).replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.strip("\n")
    if not raw.strip():
        return None
    language = None
    for class_name in code.get("class", ()):
        if class_name.startswith("language-"):
            language = class_name.removeprefix("language-")
            break
    fence = f"```{language or ''}\n{raw}\n```"
    return ContentBlock(kind="code", text=fence, language=language)


def _render_blocks(container: Tag) -> tuple[ContentBlock, ...]:
    blocks: list[ContentBlock] = []
    inline: list[str] = []

    def flush_inline() -> None:
        text = _normalize_text(" ".join(inline))
        inline.clear()
        if text:
            blocks.append(ContentBlock(kind="paragraph", text=text))

    def visit(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            text = str(node)
            if text.strip():
                inline.append(text)
            return
        if not isinstance(node, Tag):
            return
        name = node.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return
        if name == "pre":
            flush_inline()
            rendered = _render_code(node)
            if rendered:
                blocks.append(rendered)
            return
        if name == "table":
            flush_inline()
            rendered = _render_table(node)
            if rendered:
                blocks.append(rendered)
            return
        if name in {"ul", "ol"}:
            flush_inline()
            rendered = _render_list(node)
            if rendered:
                blocks.append(rendered)
            return
        if name == "img":
            alt = _normalize_text(node.get("alt", ""))
            if alt:
                inline.append(alt)
            return
        if name == "br":
            inline.append("\n")
            return
        is_block = name in _BLOCK_CONTAINERS
        if is_block:
            flush_inline()
        for child in node.children:
            visit(child)
        if is_block:
            flush_inline()

    for child in container.children:
        visit(child)
    flush_inline()
    return tuple(block for block in blocks if block.text.strip())


def _is_question(title: str) -> bool:
    return bool(_QUESTION_PREFIX_RE.search(title) or title.rstrip().endswith(("?", "？")))


def _time_tags(text: str) -> tuple[int, ...]:
    return tuple(sorted({int(match) for match in _YEAR_RE.findall(text)}))


def _classify(item_title: str | None, content: str) -> tuple[ChunkType, str | None, tuple[int, ...]]:
    if item_title and _is_question(item_title):
        return "qa", item_title, _time_tags(f"{item_title}\n{content}")
    combined = f"{item_title or ''}\n{content}"
    tags = _time_tags(combined)
    if _TREND_RE.search(combined) or len(tags) >= 2:
        return "trend", None, tags
    if item_title:
        return "topic", None, tags
    return "article", None, tags


def _make_unit(
    *,
    source: str,
    course: str,
    lesson: str | None,
    title_path: tuple[str, ...],
    chunk_type: ChunkType,
    blocks: Iterable[ContentBlock],
    slide_start: int | None,
    slide_end: int | None,
    question: str | None = None,
    time_tags: tuple[int, ...] = (),
) -> SemanticUnit:
    return SemanticUnit(
        source=source,
        course=course,
        lesson=lesson,
        title_path=tuple(item for item in title_path if item),
        question=question,
        chunk_type=chunk_type,
        blocks=tuple(block for block in blocks if block.text.strip()),
        slide_start=slide_start,
        slide_end=slide_end,
        time_tags=time_tags,
    )


def _parse_course_map(
    soup: BeautifulSoup,
    *,
    source: str,
    course_title: str | None,
) -> ParsedAgentDocument:
    page_title = _visible_text(soup.select_one(".hero h1")) or _visible_text(soup.find("h1"))
    course = course_title or page_title or "Agent 求职指南"
    cards: list[ContentBlock] = []
    for card in soup.select(".course-card"):
        lesson_no = _visible_text(card.select_one(".lesson-no"))
        lesson_title = _visible_text(card.select_one(".lesson-title"))
        description = _visible_text(card.select_one(".lesson-desc"))
        points = [
            _visible_text(item)
            for item in card.select(".lesson-points > li")
            if _visible_text(item)
        ]
        heading = " · ".join(item for item in (lesson_no, lesson_title) if item)
        lines = [heading] if heading else []
        if description:
            lines.append(f"简介：{description}")
        if points:
            lines.append("知识点：")
            lines.extend(f"- {point}" for point in points)
        text = "\n".join(lines).strip()
        if text:
            cards.append(ContentBlock(kind="card", text=text))
    unit = _make_unit(
        source=source,
        course=course,
        lesson=None,
        title_path=(),
        chunk_type="course_overview",
        blocks=cards,
        slide_start=None,
        slide_end=None,
    )
    units = (replace(unit, unit_index=0),) if unit.content else ()
    return ParsedAgentDocument(
        source=source,
        kind="course_map",
        course_title=course,
        lesson_title=None,
        subtitle=None,
        section_titles=(),
        units=units,
    )


def _parse_reveal(
    soup: BeautifulSoup,
    *,
    source: str,
    course_title: str | None,
) -> ParsedAgentDocument:
    page_title = _visible_text(soup.find("title"))
    lesson = page_title or _visible_text(soup.select_one("h1.main-title")) or _visible_text(soup.find("h1"))
    course = course_title or "Agent 求职面试全攻略"
    subtitle = _visible_text(soup.select_one(".main-subtitle")) or None

    groups: list[_SectionGroup] = []
    current_group = _SectionGroup(title=None, h3_titles=[], details=[])
    groups.append(current_group)
    current: _DraftUnit | None = None

    def flush_current() -> None:
        nonlocal current
        if current is not None and any(block.text.strip() for block in current.blocks):
            current_group.details.append(current)
        current = None

    slides = list(soup.select("section.content-slide"))
    for slide_index, slide in enumerate(slides, 1):
        h2 = _visible_text(slide.find("h2"))
        h3 = _visible_text(slide.find("h3"))
        blocks = list(_render_blocks(slide))

        if h2:
            flush_current()
            current_group = _SectionGroup(title=h2, h3_titles=[], details=[])
            groups.append(current_group)
        if h3:
            flush_current()
            current_group.h3_titles.append(h3)
            current = _DraftUnit(
                section=current_group.title,
                item_title=h3,
                blocks=[],
                slide_start=slide_index,
                slide_end=slide_index,
            )
        if blocks:
            if current is None:
                current = _DraftUnit(
                    section=current_group.title,
                    item_title=None,
                    blocks=[],
                    slide_start=slide_index,
                    slide_end=slide_index,
                )
            current.blocks.extend(blocks)
            current.slide_end = slide_index
        elif current is not None and not h2 and not h3:
            # Blank continuation slides do not extend the meaningful range.
            pass
    flush_current()

    section_titles = tuple(group.title for group in groups if group.title)
    lesson_lines: list[str] = []
    if subtitle:
        lesson_lines.append(subtitle)
    if section_titles:
        lesson_lines.append("本讲章节：")
        lesson_lines.extend(f"- {title}" for title in section_titles)
    if not lesson_lines:
        lesson_lines.append(lesson)
    units: list[SemanticUnit] = [
        _make_unit(
            source=source,
            course=course,
            lesson=lesson,
            title_path=(),
            chunk_type="lesson_overview",
            blocks=(ContentBlock(kind="overview", text="\n".join(lesson_lines)),),
            slide_start=None,
            slide_end=None,
        )
    ]

    for group in groups:
        if group.title and len(group.h3_titles) > 1:
            overview_text = "本章覆盖：\n" + "\n".join(
                f"- {title}" for title in group.h3_titles
            )
            units.append(
                _make_unit(
                    source=source,
                    course=course,
                    lesson=lesson,
                    title_path=(group.title,),
                    chunk_type="section_overview",
                    blocks=(ContentBlock(kind="overview", text=overview_text),),
                    slide_start=None,
                    slide_end=None,
                )
            )
        for draft in group.details:
            content = "\n\n".join(block.text for block in draft.blocks)
            chunk_type, question, tags = _classify(draft.item_title, content)
            title_path = tuple(
                item for item in (draft.section, draft.item_title) if item
            )
            units.append(
                _make_unit(
                    source=source,
                    course=course,
                    lesson=lesson,
                    title_path=title_path,
                    question=question,
                    chunk_type=chunk_type,
                    blocks=draft.blocks,
                    slide_start=draft.slide_start,
                    slide_end=draft.slide_end,
                    time_tags=tags,
                )
            )

    indexed = tuple(replace(unit, unit_index=index) for index, unit in enumerate(units))
    return ParsedAgentDocument(
        source=source,
        kind="reveal",
        course_title=course,
        lesson_title=lesson,
        subtitle=subtitle,
        section_titles=section_titles,
        units=indexed,
    )


def parse_agent_doc_html(
    html: str,
    *,
    source: str,
    course_title: str | None = None,
) -> ParsedAgentDocument:
    """Parse one Agent corpus HTML document into ordered semantic units."""

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML content must be a non-empty string")
    normalized_source = _normalize_source(source)
    soup = BeautifulSoup(html, "html.parser")
    _remove_noise(soup)
    if soup.select_one(".course-card") is not None:
        return _parse_course_map(
            soup,
            source=normalized_source,
            course_title=course_title,
        )
    return _parse_reveal(
        soup,
        source=normalized_source,
        course_title=course_title,
    )


# --- Token-aware chunk construction -------------------------------------------------

from dataclasses import dataclass as _dataclass
import hashlib
from typing import Any, Protocol


class ChunkingError(ValueError):
    """Raised when semantic chunks cannot be built without violating the budget."""


class TokenizerLike(Protocol):
    """Minimal injected tokenizer surface required by the pure chunking service."""

    def count(self, text: str) -> int: ...

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]: ...


@_dataclass(frozen=True)
class ChunkingConfig:
    split_threshold_tokens: int = 1024
    target_min_tokens: int = 500
    target_max_tokens: int = 700
    fallback_overlap_tokens: int = 64

    def __post_init__(self) -> None:
        if self.split_threshold_tokens <= 0:
            raise ChunkingError("split threshold must be positive")
        if not (
            0 < self.target_min_tokens
            <= self.target_max_tokens
            <= self.split_threshold_tokens
        ):
            raise ChunkingError(
                "target token range must satisfy 0 < min <= max <= threshold"
            )
        if not (
            0 <= self.fallback_overlap_tokens < self.target_max_tokens
        ):
            raise ChunkingError("fallback overlap must be smaller than target max")


@_dataclass(frozen=True)
class _Fragment:
    text: str
    method: str
    separator_before: str = ""
    overlap_tokens: int = 0
    standalone: bool = False


_METHOD_PRIORITY = {
    "none": 0,
    "structure": 1,
    "sentence": 2,
    "clause": 3,
    "token_window": 4,
}


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embedding_header(unit: SemanticUnit) -> str:
    lines = [f"课程：{unit.course}"]
    if unit.lesson:
        lines.append(f"讲次：{unit.lesson}")

    title_path = unit.title_path
    if unit.chunk_type == "qa":
        if len(title_path) > 1:
            lines.append(f"章节：{title_path[0]}")
        if unit.question:
            lines.append(f"问题：{unit.question}")
    elif unit.chunk_type in {"topic", "trend"}:
        if len(title_path) > 1:
            lines.append(f"章节：{title_path[0]}")
            lines.append(f"专题：{title_path[-1]}")
        elif title_path:
            lines.append(f"专题：{title_path[0]}")
    elif title_path:
        lines.append(f"章节：{title_path[0]}")
    return "\n".join(lines)


def _embedding_text(header: str, content: str) -> str:
    return f"{header}\n\n{content}" if content else header


def _fits(
    header: str,
    content: str,
    tokenizer: TokenizerLike,
    limit: int,
) -> bool:
    return tokenizer.count(_embedding_text(header, content)) <= limit


def _split_on_boundaries(text: str, pattern: re.Pattern[str]) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in pattern.finditer(text):
        end = match.end()
        if end > start:
            pieces.append(text[start:end])
        start = end
    if start < len(text):
        pieces.append(text[start:])
    return [piece for piece in pieces if piece]


_SENTENCE_BOUNDARY_RE = re.compile(r"[\u3002\uFF01\uFF1F\uFF1B.!?;]+\s*")
_CLAUSE_BOUNDARY_RE = re.compile(r"[\uFF0C\u3001\uFF1A,]+\s*|\n+|\s+")


def _token_windows(
    text: str,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    try:
        offsets = tuple(
            (start, end)
            for start, end in tokenizer.offsets(text)
            if end > start
        )
    except Exception as exc:  # pragma: no cover - adapter errors are wrapped for callers
        raise ChunkingError("fast tokenizer offset mapping failed") from exc
    if not offsets:
        raise ChunkingError("fast tokenizer returned no usable offset mapping")

    prefix_tokens = tokenizer.count(f"{header}\n\n")
    body_budget = config.target_max_tokens - prefix_tokens
    if body_budget <= config.fallback_overlap_tokens:
        raise ChunkingError(
            "title context leaves no token-window budget beyond configured overlap"
        )

    fragments: list[_Fragment] = []
    token_start = 0
    while token_start < len(offsets):
        token_end = min(len(offsets), token_start + body_budget)
        char_start = 0 if token_start == 0 else offsets[token_start][0]
        char_end = len(text) if token_end == len(offsets) else offsets[token_end - 1][1]
        candidate = text[char_start:char_end]
        while token_end > token_start and not _fits(
            header,
            candidate,
            tokenizer,
            config.split_threshold_tokens,
        ):
            token_end -= 1
            char_end = offsets[token_end - 1][1]
            candidate = text[char_start:char_end]
        if token_end <= token_start or not candidate:
            raise ChunkingError("cannot fit token-window content under hard threshold")
        overlap = 0 if token_start == 0 else min(
            config.fallback_overlap_tokens, token_end - token_start
        )
        fragments.append(
            _Fragment(
                text=candidate,
                method="token_window",
                overlap_tokens=overlap,
                standalone=True,
            )
        )
        if token_end == len(offsets):
            break
        next_start = token_end - config.fallback_overlap_tokens
        if next_start <= token_start:
            raise ChunkingError("token-window overlap prevents forward progress")
        token_start = next_start
    return fragments


def _split_plain_text(
    text: str,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
    level: int = 0,
) -> list[_Fragment]:
    if _fits(header, text, tokenizer, config.split_threshold_tokens):
        method = "sentence" if level == 1 else "clause" if level >= 2 else "structure"
        return [_Fragment(text=text, method=method)]

    if level == 0:
        pieces = _split_on_boundaries(text, _SENTENCE_BOUNDARY_RE)
        if len(pieces) > 1:
            result: list[_Fragment] = []
            for piece in pieces:
                if _fits(header, piece, tokenizer, config.split_threshold_tokens):
                    result.append(_Fragment(text=piece, method="sentence"))
                else:
                    result.extend(
                        _split_plain_text(
                            piece,
                            header=header,
                            tokenizer=tokenizer,
                            config=config,
                            level=1,
                        )
                    )
            return result
        level = 1

    if level == 1:
        pieces = _split_on_boundaries(text, _CLAUSE_BOUNDARY_RE)
        if len(pieces) > 1:
            result = []
            for piece in pieces:
                if _fits(header, piece, tokenizer, config.split_threshold_tokens):
                    result.append(_Fragment(text=piece, method="clause"))
                else:
                    result.extend(
                        _split_plain_text(
                            piece,
                            header=header,
                            tokenizer=tokenizer,
                            config=config,
                            level=2,
                        )
                    )
            return result

    return _token_windows(
        text,
        header=header,
        tokenizer=tokenizer,
        config=config,
    )


def _render_list_items(block: ContentBlock) -> list[str]:
    if block.items:
        ordered = block.text.lstrip().startswith("1.")
        return [
            f"{index}. {item}" if ordered else f"- {item}"
            for index, item in enumerate(block.items, 1)
        ]
    return [line for line in block.text.splitlines() if line.strip()]


def _split_list_block(
    block: ContentBlock,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    items = _render_list_items(block)
    fragments: list[_Fragment] = []
    for item in items:
        if _fits(header, item, tokenizer, config.split_threshold_tokens):
            fragments.append(
                _Fragment(
                    text=item,
                    method="structure",
                    separator_before="\n" if fragments else "",
                )
            )
            continue
        marker, _, item_text = item.partition(" ")
        split = _split_plain_text(
            item_text or item,
            header=header,
            tokenizer=tokenizer,
            config=config,
        )
        for part in split:
            fragments.append(
                replace(
                    part,
                    text=f"{marker} {part.text}",
                    separator_before="\n" if fragments else "",
                    standalone=True,
                )
            )
    return fragments


def _table_text(header_cells: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    lines = [_markdown_row(header_cells), _markdown_row("---" for _ in header_cells)]
    lines.extend(_markdown_row(row) for row in rows)
    return "\n".join(lines)


def _split_table_block(
    block: ContentBlock,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    table_header = block.table_header
    rows = list(block.table_rows)
    if not table_header or not rows:
        return _split_plain_text(
            block.text,
            header=header,
            tokenizer=tokenizer,
            config=config,
        )

    groups: list[list[tuple[str, ...]]] = []
    current: list[tuple[str, ...]] = []
    for row in rows:
        candidate_rows = [*current, row]
        candidate = _table_text(table_header, candidate_rows)
        current_tokens = tokenizer.count(_embedding_text(header, _table_text(table_header, current))) if current else 0
        if current and not (
            _fits(header, candidate, tokenizer, config.target_max_tokens)
            or (
                current_tokens < config.target_min_tokens
                and _fits(header, candidate, tokenizer, config.split_threshold_tokens)
            )
        ):
            groups.append(current)
            current = []
            candidate_rows = [row]
            candidate = _table_text(table_header, candidate_rows)
        if not _fits(header, candidate, tokenizer, config.split_threshold_tokens):
            if current:
                groups.append(current)
                current = []
            row_text = _markdown_row(row)
            for part in _split_plain_text(
                row_text,
                header=header,
                tokenizer=tokenizer,
                config=config,
            ):
                wrapped = _table_text(table_header, ((part.text,),))
                if not _fits(header, wrapped, tokenizer, config.split_threshold_tokens):
                    raise ChunkingError("single table row cannot fit under hard threshold")
                groups.append(((part.text,),))
        else:
            current.append(row)
    if current:
        groups.append(current)

    return [
        _Fragment(
            text=_table_text(table_header, rows_group),
            method="structure",
            standalone=True,
        )
        for rows_group in groups
    ]


def _unwrap_code(block: ContentBlock) -> str:
    lines = block.text.splitlines()
    if lines and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return block.text


def _wrap_code(text: str, language: str | None) -> str:
    return f"```{language or ''}\n{text}\n```"


def _code_token_windows(
    text: str,
    *,
    language: str | None,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    """Fallback for one code line while preserving exact source slices and fences."""

    offsets = tuple(
        (start, end)
        for start, end in tokenizer.offsets(text)
        if end > start
    )
    if not offsets:
        raise ChunkingError("fast tokenizer returned no usable code offset mapping")
    fixed_tokens = tokenizer.count(
        _embedding_text(header, _wrap_code("", language))
    )
    body_budget = config.target_max_tokens - fixed_tokens
    if body_budget <= config.fallback_overlap_tokens:
        raise ChunkingError(
            "title and code fence leave no token-window budget beyond overlap"
        )

    fragments: list[_Fragment] = []
    token_start = 0
    while token_start < len(offsets):
        token_end = min(len(offsets), token_start + body_budget)
        char_start = 0 if token_start == 0 else offsets[token_start][0]
        char_end = len(text) if token_end == len(offsets) else offsets[token_end - 1][1]
        raw = text[char_start:char_end]
        wrapped = _wrap_code(raw, language)
        while token_end > token_start and not _fits(
            header,
            wrapped,
            tokenizer,
            config.split_threshold_tokens,
        ):
            token_end -= 1
            char_end = offsets[token_end - 1][1]
            raw = text[char_start:char_end]
            wrapped = _wrap_code(raw, language)
        if token_end <= token_start or not raw:
            raise ChunkingError("cannot fit code token window under hard threshold")
        fragments.append(
            _Fragment(
                text=wrapped,
                method="token_window",
                overlap_tokens=(
                    0
                    if token_start == 0
                    else min(config.fallback_overlap_tokens, token_end - token_start)
                ),
                standalone=True,
            )
        )
        if token_end == len(offsets):
            break
        next_start = token_end - config.fallback_overlap_tokens
        if next_start <= token_start:
            raise ChunkingError("code token-window overlap prevents forward progress")
        token_start = next_start
    return fragments

def _split_code_block(
    block: ContentBlock,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    body = _unwrap_code(block)
    groups = [group for group in re.split(r"\n\s*\n", body) if group]
    if len(groups) <= 1:
        groups = body.splitlines()
    fragments: list[_Fragment] = []
    current: list[str] = []
    joiner = "\n\n" if "\n\n" in body else "\n"
    for group in groups:
        candidate_groups = [*current, group]
        candidate = _wrap_code(joiner.join(candidate_groups), block.language)
        current_text = _wrap_code(joiner.join(current), block.language) if current else ""
        current_tokens = tokenizer.count(_embedding_text(header, current_text)) if current else 0
        if current and not (
            _fits(header, candidate, tokenizer, config.target_max_tokens)
            or (
                current_tokens < config.target_min_tokens
                and _fits(header, candidate, tokenizer, config.split_threshold_tokens)
            )
        ):
            fragments.append(
                _Fragment(
                    text=current_text,
                    method="structure",
                    standalone=True,
                )
            )
            current = []
            candidate = _wrap_code(group, block.language)
        if not _fits(header, candidate, tokenizer, config.split_threshold_tokens):
            if current:
                fragments.append(
                    _Fragment(
                        text=_wrap_code(joiner.join(current), block.language),
                        method="structure",
                        standalone=True,
                    )
                )
                current = []
            fragments.extend(
                _code_token_windows(
                    group,
                    language=block.language,
                    header=header,
                    tokenizer=tokenizer,
                    config=config,
                )
            )
        else:
            current.append(group)
    if current:
        fragments.append(
            _Fragment(
                text=_wrap_code(joiner.join(current), block.language),
                method="structure",
                standalone=True,
            )
        )
    return fragments


def _block_fragments(
    block: ContentBlock,
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[_Fragment]:
    if _fits(header, block.text, tokenizer, config.split_threshold_tokens):
        return [_Fragment(text=block.text, method="structure")]
    if block.kind == "list":
        return _split_list_block(
            block, header=header, tokenizer=tokenizer, config=config
        )
    if block.kind == "table":
        return _split_table_block(
            block, header=header, tokenizer=tokenizer, config=config
        )
    if block.kind == "code":
        return _split_code_block(
            block, header=header, tokenizer=tokenizer, config=config
        )
    return _split_plain_text(
        block.text,
        header=header,
        tokenizer=tokenizer,
        config=config,
    )


def _combine_method(left: str, right: str) -> str:
    return left if _METHOD_PRIORITY[left] >= _METHOD_PRIORITY[right] else right


def _pack_fragments(
    fragments: list[_Fragment],
    *,
    header: str,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[tuple[str, str, int]]:
    packed: list[tuple[str, str, int]] = []
    current_text = ""
    current_method = "structure"

    def flush() -> None:
        nonlocal current_text, current_method
        if current_text:
            packed.append((current_text, current_method, 0))
        current_text = ""
        current_method = "structure"

    for fragment in fragments:
        if fragment.standalone:
            flush()
            packed.append((fragment.text, fragment.method, fragment.overlap_tokens))
            continue
        candidate = (
            f"{current_text}{fragment.separator_before}{fragment.text}"
            if current_text
            else fragment.text
        )
        if not current_text:
            current_text = candidate
            current_method = fragment.method
            continue
        current_tokens = tokenizer.count(_embedding_text(header, current_text))
        can_add = _fits(header, candidate, tokenizer, config.target_max_tokens)
        if not can_add and current_tokens < config.target_min_tokens:
            can_add = _fits(
                header,
                candidate,
                tokenizer,
                config.split_threshold_tokens,
            )
        if can_add:
            current_text = candidate
            current_method = _combine_method(current_method, fragment.method)
        else:
            flush()
            current_text = fragment.text
            current_method = fragment.method
    flush()
    return packed


def _split_unit(
    unit: SemanticUnit,
    tokenizer: TokenizerLike,
    config: ChunkingConfig,
) -> list[tuple[str, str, int]]:
    content = unit.content
    if not content.strip():
        raise ChunkingError(f"semantic unit has empty content: {unit.parent_key}")
    header = _embedding_header(unit)
    if tokenizer.count(header) > config.split_threshold_tokens:
        raise ChunkingError(
            f"title context exceeds hard threshold for {unit.parent_key}"
        )
    if _fits(header, content, tokenizer, config.split_threshold_tokens):
        return [(content, "none", 0)]

    if unit.chunk_type == "course_overview":
        course_fragments: list[_Fragment] = []
        for block_index, block in enumerate(unit.blocks):
            if block.kind != "card" or not _fits(
                header,
                block.text,
                tokenizer,
                config.split_threshold_tokens,
            ):
                raise ChunkingError(
                    f"course card exceeds hard threshold for {unit.parent_key}"
                )
            course_fragments.append(
                _Fragment(
                    text=block.text,
                    method="structure",
                    separator_before="\n\n" if block_index else "",
                )
            )
        return _pack_fragments(
            course_fragments,
            header=header,
            tokenizer=tokenizer,
            config=config,
        )

    fragments: list[_Fragment] = []
    for block_index, block in enumerate(unit.blocks):
        block_parts = _block_fragments(
            block,
            header=header,
            tokenizer=tokenizer,
            config=config,
        )
        if not block_parts:
            continue
        if block_index > 0 and not block_parts[0].standalone:
            block_parts[0] = replace(block_parts[0], separator_before="\n\n")
        fragments.extend(block_parts)
    packed = _pack_fragments(
        fragments,
        header=header,
        tokenizer=tokenizer,
        config=config,
    )
    if not packed:
        raise ChunkingError(f"semantic unit produced no chunks: {unit.parent_key}")
    for text, _, _ in packed:
        if not _fits(header, text, tokenizer, config.split_threshold_tokens):
            raise ChunkingError(
                f"split child exceeds hard threshold for {unit.parent_key}"
            )
    return packed


def build_chunk_records(
    units: Iterable[SemanticUnit],
    tokenizer: TokenizerLike,
    config: ChunkingConfig | None = None,
) -> list[dict[str, Any]]:
    """Split semantic units and return deterministic JSON-serializable records."""

    config = config or ChunkingConfig()
    records: list[dict[str, Any]] = []
    for unit in sorted(units, key=lambda item: (item.source, item.unit_index)):
        header = _embedding_header(unit)
        parts = _split_unit(unit, tokenizer, config)
        part_count = len(parts)
        for part_index, (content, split_method, overlap_tokens) in enumerate(parts):
            embedding_text = _embedding_text(header, content)
            parent_id = unit.parent_key
            record = {
                "schema_version": 1,
                "chunk_id": f"{parent_id}#part-{part_index:02d}",
                "parent_id": parent_id,
                "chunk_type": unit.chunk_type,
                "source": unit.source,
                "course": unit.course,
                "lesson": unit.lesson,
                "title_path": list(unit.title_path),
                "question": unit.question if unit.chunk_type == "qa" else None,
                "time_tags": list(unit.time_tags),
                "slide_start": unit.slide_start,
                "slide_end": unit.slide_end,
                "unit_index": unit.unit_index,
                "part_index": part_index,
                "part_count": part_count,
                "contains_code": "```" in content,
                "split_method": split_method,
                "overlap_tokens": overlap_tokens,
                "content_token_count": tokenizer.count(content),
                "embedding_token_count": tokenizer.count(embedding_text),
                "content": content,
                "embedding_text": embedding_text,
                "content_sha256": _sha256_prefixed(content),
            }
            records.append(record)
    records.sort(key=lambda item: (item["source"], item["unit_index"], item["part_index"]))
    validate_chunk_records(records, tokenizer, config)
    return records


def validate_chunk_records(
    records: Iterable[dict[str, Any]],
    tokenizer: TokenizerLike,
    config: ChunkingConfig | None = None,
) -> None:
    """Validate record schema, ordering, hashes, and exact tokenizer counts."""

    config = config or ChunkingConfig()
    materialized = list(records)
    if not materialized:
        raise ChunkingError("chunk build produced zero records")
    expected_order = sorted(
        materialized,
        key=lambda item: (item["source"], item["unit_index"], item["part_index"]),
    )
    if materialized != expected_order:
        raise ChunkingError("chunk records are not in deterministic order")
    seen_ids: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in materialized:
        chunk_id = record.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id in seen_ids:
            raise ChunkingError("chunk IDs must be non-empty and unique")
        seen_ids.add(chunk_id)
        source = record.get("source")
        if not isinstance(source, str) or "\\" in source or PurePosixPath(source).is_absolute():
            raise ChunkingError(f"source must be a relative POSIX path: {source!r}")
        content = record.get("content")
        embedding_text = record.get("embedding_text")
        if not isinstance(content, str) or not content.strip():
            raise ChunkingError(f"chunk has empty content: {chunk_id}")
        if not isinstance(embedding_text, str) or not embedding_text.strip():
            raise ChunkingError(f"chunk has empty embedding text: {chunk_id}")
        if record.get("content_token_count") != tokenizer.count(content):
            raise ChunkingError(f"content token count mismatch: {chunk_id}")
        embedding_count = tokenizer.count(embedding_text)
        if record.get("embedding_token_count") != embedding_count:
            raise ChunkingError(f"embedding token count mismatch: {chunk_id}")
        if embedding_count > config.split_threshold_tokens:
            raise ChunkingError(f"chunk exceeds hard threshold: {chunk_id}")
        if record.get("content_sha256") != _sha256_prefixed(content):
            raise ChunkingError(f"content hash mismatch: {chunk_id}")
        title_path = record.get("title_path")
        if not isinstance(title_path, list) or any(
            not isinstance(item, str) or not item for item in title_path
        ):
            raise ChunkingError(f"invalid title path: {chunk_id}")
        if record.get("chunk_type") == "qa":
            if not record.get("question"):
                raise ChunkingError(f"qa chunk lacks question: {chunk_id}")
        elif record.get("question") is not None:
            raise ChunkingError(f"non-qa chunk has question: {chunk_id}")
        method = record.get("split_method")
        if method not in _METHOD_PRIORITY:
            raise ChunkingError(f"invalid split method: {chunk_id}")
        overlap = record.get("overlap_tokens")
        if not isinstance(overlap, int) or overlap < 0:
            raise ChunkingError(f"invalid overlap: {chunk_id}")
        if overlap and method != "token_window":
            raise ChunkingError(f"overlap is only valid for token windows: {chunk_id}")
        groups.setdefault(record["parent_id"], []).append(record)

    for parent_id, group in groups.items():
        part_count = len(group)
        if [item["part_index"] for item in group] != list(range(part_count)):
            raise ChunkingError(f"non-contiguous part indexes: {parent_id}")
        if any(item["part_count"] != part_count for item in group):
            raise ChunkingError(f"part count mismatch: {parent_id}")
        if any(item["parent_id"] != parent_id for item in group):
            raise ChunkingError(f"parent ID mismatch: {parent_id}")

