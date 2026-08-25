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
    """Ordered text blocks for one physical or virtual 1-based page."""

    page_number: int
    width: float
    height: float
    blocks: tuple[ParsedTextBlock, ...]
    locator_start: int | None = None
    locator_end: int | None = None
    locator: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "page_number": self.page_number,
            "width": float(self.width),
            "height": float(self.height),
            "blocks": [block.to_dict() for block in self.blocks],
        }
        if self.locator_start is not None:
            payload["locator_start"] = self.locator_start
        if self.locator_end is not None:
            payload["locator_end"] = self.locator_end
        if self.locator is not None:
            payload["locator"] = self.locator
        return payload


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Stable, JSON-serializable representation of extracted attachment text."""

    schema_version: int
    document_id: str
    original_filename: str
    page_count: int
    extracted_char_count: int
    pages: tuple[ParsedPage, ...]
    content_kind: str = "pdf"
    locator_unit: str = "page"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "page_count": self.page_count,
            "extracted_char_count": self.extracted_char_count,
            "pages": [page.to_dict() for page in self.pages],
        }
        if self.schema_version >= 2:
            payload["content_kind"] = self.content_kind
            payload["locator_unit"] = self.locator_unit
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParsedDocument":
        """Deserialize and strictly validate schema version 1 or 2 JSON."""

        if not isinstance(payload, Mapping):
            raise ParsedDocumentValidationError(
                "Parsed document payload must be an object"
            )
        schema_version = _required_int(payload, "schema_version", minimum=1)
        if schema_version not in {1, 2}:
            raise ParsedDocumentValidationError(
                "Unsupported parsed document schema_version"
            )
        content_kind = _optional_choice(
            payload,
            "content_kind",
            default="pdf",
            allowed={
                "pdf", "text", "markdown", "csv", "json", "html", "docx",
                "xlsx", "pptx", "code", "log",
            },
        )
        locator_unit = _optional_choice(
            payload,
            "locator_unit",
            default="page",
            allowed={"page", "section", "line", "row", "sheet", "slide", "paragraph"},
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
            locator_start = _optional_int(raw_page, "locator_start", minimum=1)
            locator_end = _optional_int(raw_page, "locator_end", minimum=1)
            if (locator_start is None) != (locator_end is None):
                raise ParsedDocumentValidationError(
                    "locator_start and locator_end must be provided together"
                )
            if locator_start is not None and locator_end is not None and locator_end < locator_start:
                raise ParsedDocumentValidationError(
                    "locator_end must be greater than or equal to locator_start"
                )
            locator = _optional_text(raw_page, "locator")
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
                    locator_start=locator_start,
                    locator_end=locator_end,
                    locator=locator,
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
            content_kind=content_kind,
            locator_unit=locator_unit,
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


def _optional_int(
    payload: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
) -> int | None:
    if key not in payload:
        return None
    return _required_int(payload, key, minimum=minimum)


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    if key not in payload:
        return None
    return _required_text(payload, key)


def _optional_choice(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: str,
    allowed: set[str],
) -> str:
    value = payload.get(key, default)
    if value not in allowed:
        raise ParsedDocumentValidationError(f"{key} is not supported")
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
