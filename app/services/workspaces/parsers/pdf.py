"""PDF parser adapter backed by the existing PyMuPDF parser."""

from pathlib import Path

from app.services.documents.pdf_parser import PdfParser
from app.services.workspaces.asset_settings import WorkspaceAssetSettings
from app.services.workspaces.parsed_asset import ParsedAsset
from app.services.workspaces.parsers.base import segment_text


def parse_pdf(path: Path, *, asset_id: str, media_type: str, original_filename: str, settings: WorkspaceAssetSettings) -> ParsedAsset:
    parsed = PdfParser().parse(
        path,
        document_id=asset_id,
        original_filename=original_filename,
        max_pages=settings.max_pdf_pages,
        min_extracted_chars=1,
        max_extracted_chars=settings.max_parsed_chars,
        max_blocks_per_page=5_000,
    )
    segments = []
    for page in parsed.pages:
        page_text = "\n".join(block.text for block in page.blocks)
        segments.extend(segment_text(page_text, locator={"page": page.page_number}))
    return ParsedAsset(asset_id, media_type, "pdf", "1", tuple(segments))
