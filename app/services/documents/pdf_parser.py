"""PyMuPDF-backed validation and ordered Page/Block text extraction."""

from pathlib import Path
import re

import pymupdf

from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)


class PdfParsingError(RuntimeError):
    """Base class for stable PDF parsing failures."""

    error_code = "PDF_PARSE_FAILED"


class InvalidPdfError(PdfParsingError):
    error_code = "INVALID_PDF"


class EncryptedPdfNotSupported(PdfParsingError):
    error_code = "ENCRYPTED_PDF_NOT_SUPPORTED"


class PdfPageLimitExceeded(PdfParsingError):
    error_code = "PDF_PAGE_LIMIT_EXCEEDED"


class NoExtractableText(PdfParsingError):
    error_code = "NO_EXTRACTABLE_TEXT"


class PdfParseFailed(PdfParsingError):
    error_code = "PDF_PARSE_FAILED"


class PdfParser:
    """Open PDF paths directly and return storage-independent parsed models."""

    name = "pymupdf"
    version = pymupdf.__version__

    def parse(
        self,
        source_path: Path,
        document_id: str,
        original_filename: str,
        max_pages: int,
        min_extracted_chars: int,
    ) -> ParsedDocument:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if min_extracted_chars <= 0:
            raise ValueError("min_extracted_chars must be positive")

        try:
            document = pymupdf.open(Path(source_path))
        except Exception as exc:
            raise InvalidPdfError("PDF could not be opened or is invalid") from exc

        try:
            if not document.is_pdf:
                raise InvalidPdfError("Opened document is not a PDF")
            if document.needs_pass or document.is_encrypted:
                raise EncryptedPdfNotSupported(
                    "Encrypted PDFs are not supported"
                )

            page_count = int(document.page_count)
            if page_count > max_pages:
                raise PdfPageLimitExceeded(
                    f"PDF has {page_count} pages; limit is {max_pages}"
                )

            pages: list[ParsedPage] = []
            extracted_char_count = 0
            for page_index in range(page_count):
                page = document.load_page(page_index)
                blocks: list[ParsedTextBlock] = []
                for raw_block in page.get_text("blocks", sort=True):
                    if len(raw_block) < 7 or int(raw_block[6]) != 0:
                        continue
                    text = _normalize_block_text(str(raw_block[4]))
                    if not text:
                        continue
                    blocks.append(
                        ParsedTextBlock(
                            block_index=len(blocks),
                            text=text,
                            bbox=tuple(
                                float(raw_block[index]) for index in range(4)
                            ),
                        )
                    )
                    extracted_char_count += sum(
                        not character.isspace() for character in text
                    )

                pages.append(
                    ParsedPage(
                        page_number=page_index + 1,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=tuple(blocks),
                    )
                )

            if extracted_char_count < min_extracted_chars:
                raise NoExtractableText(
                    "PDF does not contain enough extractable text"
                )

            return ParsedDocument(
                schema_version=1,
                document_id=document_id,
                original_filename=original_filename,
                page_count=page_count,
                extracted_char_count=extracted_char_count,
                pages=tuple(pages),
            )
        except PdfParsingError:
            raise
        except Exception as exc:
            raise PdfParseFailed("Unexpected PDF parsing failure") from exc
        finally:
            document.close()


def _normalize_block_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized)
    return normalized.strip()
