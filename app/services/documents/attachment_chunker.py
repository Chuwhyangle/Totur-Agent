"""Deterministic page-aware chunking for parsed PDF attachments."""

from dataclasses import dataclass

from app.services.documents.parsed_document import ParsedDocument


class AttachmentChunkingError(ValueError):
    """Parsed content cannot be converted into safe retrieval chunks."""


@dataclass(frozen=True, slots=True)
class AttachmentChunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    original_filename: str


class AttachmentChunker:
    """Combine ordered blocks without crossing page boundaries."""

    def __init__(self, chunk_chars: int = 2_000, overlap_chars: int = 300) -> None:
        if isinstance(chunk_chars, bool) or chunk_chars <= 0:
            raise AttachmentChunkingError("chunk_chars must be positive")
        if (
            isinstance(overlap_chars, bool)
            or overlap_chars < 0
            or overlap_chars >= chunk_chars
        ):
            raise AttachmentChunkingError(
                "overlap_chars must satisfy 0 <= overlap < chunk_chars"
            )
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars

    def chunk(self, document: ParsedDocument) -> list[AttachmentChunk]:
        chunks: list[AttachmentChunk] = []

        def append_chunk(text: str, page_number: int) -> None:
            normalized = text.strip()
            if not normalized:
                return
            chunk_index = len(chunks)
            chunks.append(
                AttachmentChunk(
                    chunk_id=f"{document.document_id}:{chunk_index}",
                    document_id=document.document_id,
                    chunk_index=chunk_index,
                    text=normalized,
                    page_start=page_number,
                    page_end=page_number,
                    original_filename=document.original_filename,
                )
            )

        for page in document.pages:
            pending = ""
            for block in page.blocks:
                text = block.text.strip()
                if not text:
                    continue

                if len(text) > self.chunk_chars:
                    append_chunk(pending, page.page_number)
                    pending = ""
                    for window in self._long_block_windows(text):
                        append_chunk(window, page.page_number)
                    continue

                candidate = f"{pending}\n\n{text}" if pending else text
                if len(candidate) <= self.chunk_chars:
                    pending = candidate
                else:
                    append_chunk(pending, page.page_number)
                    pending = text

            append_chunk(pending, page.page_number)

        return chunks

    def _long_block_windows(self, text: str):
        start = 0
        while start < len(text):
            end = min(start + self.chunk_chars, len(text))
            yield text[start:end]
            if end == len(text):
                break
            start = end - self.overlap_chars
