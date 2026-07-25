"""Pure-Python models for structured PDF text extraction results."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedTextBlock:
    """One ordered text block extracted from a PDF page."""

    block_index: int
    text: str
    bbox: tuple[float, float, float, float]
    block_type: str = "text"

    def to_dict(self) -> dict[str, object]:
        return {
            "block_index": self.block_index,
            "block_type": self.block_type,
            "bbox": [float(value) for value in self.bbox],
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class ParsedPage:
    """Ordered text blocks and dimensions for one 1-based PDF page."""

    page_number: int
    width: float
    height: float
    blocks: tuple[ParsedTextBlock, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "width": float(self.width),
            "height": float(self.height),
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Stable, JSON-serializable representation of extracted PDF text."""

    schema_version: int
    document_id: str
    original_filename: str
    page_count: int
    extracted_char_count: int
    pages: tuple[ParsedPage, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "page_count": self.page_count,
            "extracted_char_count": self.extracted_char_count,
            "pages": [page.to_dict() for page in self.pages],
        }
