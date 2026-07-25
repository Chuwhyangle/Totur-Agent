"""Pure-Python models and validation for structured PDF text results."""

from dataclasses import dataclass
import math
from typing import Any, Mapping


class ParsedDocumentValidationError(ValueError):
    """Parsed JSON violates the stable schema or record identity."""


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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParsedDocument":
        """Deserialize and strictly validate schema version 1 JSON."""

        if not isinstance(payload, Mapping):
            raise ParsedDocumentValidationError(
                "Parsed document payload must be an object"
            )
        schema_version = _required_int(payload, "schema_version", minimum=1)
        if schema_version != 1:
            raise ParsedDocumentValidationError(
                "Unsupported parsed document schema_version"
            )
        document_id = _required_text(payload, "document_id")
        original_filename = _required_text(payload, "original_filename")
        page_count = _required_int(payload, "page_count", minimum=0)
        extracted_char_count = _required_int(
            payload,
            "extracted_char_count",
            minimum=0,
        )
        raw_pages = payload.get("pages")
        if not isinstance(raw_pages, list):
            raise ParsedDocumentValidationError("pages must be an array")
        if page_count != len(raw_pages):
            raise ParsedDocumentValidationError(
                "page_count must equal the number of pages"
            )

        pages: list[ParsedPage] = []
        calculated_chars = 0
        for expected_page_number, raw_page in enumerate(raw_pages, start=1):
            if not isinstance(raw_page, Mapping):
                raise ParsedDocumentValidationError("Each page must be an object")
            page_number = _required_int(raw_page, "page_number", minimum=1)
            if page_number != expected_page_number:
                raise ParsedDocumentValidationError(
                    "page_number values must be continuous and 1-based"
                )
            width = _required_finite_number(raw_page, "width")
            height = _required_finite_number(raw_page, "height")
            raw_blocks = raw_page.get("blocks")
            if not isinstance(raw_blocks, list):
                raise ParsedDocumentValidationError("blocks must be an array")

            blocks: list[ParsedTextBlock] = []
            for expected_block_index, raw_block in enumerate(raw_blocks):
                if not isinstance(raw_block, Mapping):
                    raise ParsedDocumentValidationError(
                        "Each text block must be an object"
                    )
                block_index = _required_int(
                    raw_block,
                    "block_index",
                    minimum=0,
                )
                if block_index != expected_block_index:
                    raise ParsedDocumentValidationError(
                        "block_index values must be continuous and 0-based per page"
                    )
                text = _required_text(raw_block, "text")
                block_type = raw_block.get("block_type", "text")
                if block_type != "text":
                    raise ParsedDocumentValidationError(
                        "Only text blocks are supported"
                    )
                raw_bbox = raw_block.get("bbox")
                if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
                    raise ParsedDocumentValidationError(
                        "bbox must contain exactly four finite numbers"
                    )
                bbox = tuple(_finite_number(value, "bbox") for value in raw_bbox)
                blocks.append(
                    ParsedTextBlock(
                        block_index=block_index,
                        text=text,
                        bbox=bbox,
                        block_type="text",
                    )
                )
                calculated_chars += sum(
                    not character.isspace() for character in text
                )

            pages.append(
                ParsedPage(
                    page_number=page_number,
                    width=width,
                    height=height,
                    blocks=tuple(blocks),
                )
            )

        if extracted_char_count != calculated_chars:
            raise ParsedDocumentValidationError(
                "extracted_char_count does not match block text"
            )

        return cls(
            schema_version=schema_version,
            document_id=document_id,
            original_filename=original_filename,
            page_count=page_count,
            extracted_char_count=extracted_char_count,
            pages=tuple(pages),
        )

    def validate_identity(
        self,
        *,
        document_id: str,
        original_filename: str,
        page_count: int | None = None,
    ) -> None:
        """Require parsed output to belong to its trusted SQLite record."""

        if self.document_id != document_id:
            raise ParsedDocumentValidationError(
                "Parsed document_id does not match metadata"
            )
        if self.original_filename != original_filename:
            raise ParsedDocumentValidationError(
                "Parsed original_filename does not match metadata"
            )
        if page_count is not None and self.page_count != page_count:
            raise ParsedDocumentValidationError(
                "Parsed page_count does not match metadata"
            )


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ParsedDocumentValidationError(f"{key} must be a non-empty string")
    return value


def _required_int(
    payload: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ParsedDocumentValidationError(
            f"{key} must be an integer >= {minimum}"
        )
    return value


def _required_finite_number(payload: Mapping[str, Any], key: str) -> float:
    return _finite_number(payload.get(key), key)


def _finite_number(value: Any, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParsedDocumentValidationError(f"{key} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ParsedDocumentValidationError(f"{key} must be a finite number")
    return normalized
