"""学习笔记 Markdown 分块器。"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.rag_settings import CHUNK_OVERLAP, CHUNK_SIZE


HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
TITLE_PATH_SEPARATOR = " > "


@dataclass(frozen=True)
class KnowledgeChunk:
    """一段可进入向量索引的学习笔记文本。"""

    content: str
    source: str
    title_path: str
    chunk_index: int

    @property
    def chunk_id(self) -> str:
        """生成确定性块 ID，保证同一文件重建索引时不会产生重复数据。"""

        return f"{self.source}#{self.chunk_index}"


def chunk_markdown(
    text: str,
    source: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[KnowledgeChunk]:
    """把 Markdown 文本按标题章节切成 KnowledgeChunk 列表。"""

    _validate_window(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks: list[KnowledgeChunk] = []
    title_stack: list[str] = []
    section_lines: list[str] = []
    section_title_path = ""

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
            )
        )
        section_lines = []

    for line in text.splitlines():
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


def _chunks_from_section(
    lines: list[str],
    source: str,
    title_path: str,
    start_index: int,
    chunk_size: int,
    chunk_overlap: int,
) -> list[KnowledgeChunk]:
    """把一个标题章节转换成一个或多个分块。"""

    if not lines:
        return []

    content = "\n".join(lines).strip()
    if not content:
        return []

    if title_path and _section_body(lines) == "":
        # 只有标题、没有正文的空章节不进入索引，避免污染检索结果。
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
        )
        for index, piece in enumerate(pieces)
    ]


def _section_body(lines: list[str]) -> str:
    """返回章节正文；有标题的章节会排除第一行标题。"""

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
    """切分章节内容；标题章节的每个长块都重复带上标题行。"""

    if len(content) <= chunk_size:
        return [content]

    if not title_path or not HEADING_PATTERN.match(lines[0]):
        return _split_with_overlap(
            content=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    title_line = lines[0].strip()
    body = _section_body(lines)
    body_chunk_size = chunk_size - len(title_line) - 1
    if body_chunk_size <= 0:
        # 极端长标题无法安全前置到每个块，只能退回普通滑窗，避免死循环。
        return _split_with_overlap(
            content=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    body_overlap = min(chunk_overlap, max(0, body_chunk_size - 1))
    body_pieces = _split_with_overlap(
        content=body,
        chunk_size=body_chunk_size,
        chunk_overlap=body_overlap,
    )

    return [f"{title_line}\n{piece}".strip() for piece in body_pieces]


def _split_with_overlap(
    content: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """按固定窗口切分文本，并保留相邻窗口重叠。"""

    if len(content) <= chunk_size:
        return [content]

    pieces = []
    start = 0
    step = chunk_size - chunk_overlap

    while start < len(content):
        end = start + chunk_size
        piece = content[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(content):
            break
        start += step

    return pieces


def _validate_window(chunk_size: int, chunk_overlap: int) -> None:
    """校验滑窗参数，避免出现无法前进的切分循环。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")
