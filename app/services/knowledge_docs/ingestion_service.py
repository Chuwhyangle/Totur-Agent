"""Durable ingestion orchestration for user knowledge documents."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from typing import Any, BinaryIO
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.models import KnowledgeDocumentRecord, KnowledgeDocumentStatus
import app.repositories.knowledge_document_repository as document_repository
from app.repositories.user_document_vector_repository import (
    UserDocumentVectorRepository,
)
from app.services.documents.pdf_markdown_converter import (
    parsed_pdf_to_markdown,
    strip_page_sentinels,
)
from app.services.documents.pdf_parser import PdfParser, PdfParsingError
from app.services.knowledge_chunker import KnowledgeChunk, chunk_markdown
from app.services.knowledge_docs.storage import KnowledgeDocumentStorage
from app.services.documents.settings import load_temporary_document_settings
from app.services.rag_settings import EMBEDDING_BATCH_SIZE


INVALID_ENCODING = "INVALID_ENCODING"
DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
EMBEDDING_FAILED = "EMBEDDING_FAILED"
VECTOR_INDEX_FAILED = "VECTOR_INDEX_FAILED"
INGESTION_FAILED = "INGESTION_FAILED"


class KnowledgeDocumentIngestionError(RuntimeError):
    """Base orchestration failure."""


class KnowledgeDocumentIngestionService:
    """Run storage, parsing, deduplication, embedding, and publishing."""

    def __init__(
        self,
        repository: Any | None = None,
        vector_repository: Any | None = None,
        embedding_client: Any | None = None,
        storage: Any | None = None,
        pdf_parser: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self.repository = repository or document_repository
        self.vector_repository = vector_repository or UserDocumentVectorRepository()
        self.embedding_client = embedding_client or EmbeddingClient()
        self.storage = storage or KnowledgeDocumentStorage()
        self.pdf_parser = pdf_parser or PdfParser()
        self.settings = settings or load_temporary_document_settings()

    def ingest_document(
        self,
        user_id: str,
        original_filename: str,
        media_type: str,
        file_stream: BinaryIO,
    ) -> tuple[KnowledgeDocumentRecord, bool]:
        storage_key, size_bytes, file_sha256 = self.storage.stage_upload(
            file_stream, original_filename, media_type
        )
        duplicate = self.repository.get_active_by_file_hash(user_id, file_sha256)
        if duplicate is not None:
            self.storage.delete(storage_key)
            return duplicate, True

        previous = self.repository.get_latest_by_filename(user_id, original_filename)
        document_id = str(uuid4())
        now = _now()
        record = KnowledgeDocumentRecord(
            id=document_id,
            user_id=user_id,
            original_filename=original_filename.strip(),
            media_type=media_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            file_sha256=file_sha256,
            text_sha256=None,
            dedupe_key=file_sha256,
            version_no=(previous.version_no + 1 if previous else 1),
            status=KnowledgeDocumentStatus.UPLOADED,
            page_count=None,
            chunk_count=None,
            parser_name=None,
            parser_version=None,
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        try:
            self.repository.insert_uploaded(record)
        except IntegrityError:
            duplicate = self.repository.get_active_by_file_hash(user_id, file_sha256)
            if duplicate is not None:
                self.storage.delete(storage_key)
                return duplicate, True
            self.storage.delete(storage_key)
            raise

        return self._process(record, previous.id if previous else None), False

    def reprocess_document(self, document_id: str) -> KnowledgeDocumentRecord:
        record = self.repository.get_document(document_id)
        if record is None:
            raise KnowledgeDocumentIngestionError("Knowledge document not found")
        if record.status in (
            KnowledgeDocumentStatus.DELETED,
            KnowledgeDocumentStatus.READY,
        ):
            return record
        return self._process(record, None)

    def _process(
        self,
        record: KnowledgeDocumentRecord,
        old_document_id: str | None,
    ) -> KnowledgeDocumentRecord:
        current = self._transition(record, KnowledgeDocumentStatus.PARSING)
        if current is None:
            return self.repository.get_document(record.id) or record
        record = current
        vectors_written = False
        try:
            text, page_count, parser_name, parser_version = self._extract(record)
        except UnicodeDecodeError as exc:
            return self._failed(record, INVALID_ENCODING, "Markdown 文件不是有效的 UTF-8", exc)
        except PdfParsingError as exc:
            return self._failed(record, getattr(exc, "error_code", "PDF_PARSE_FAILED"), str(exc), exc)
        except Exception as exc:
            return self._failed(record, INGESTION_FAILED, "文档解析失败", exc)

        text_sha256 = sha256(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()
        duplicate = self.repository.get_active_by_text_hash(record.user_id, text_sha256)
        if duplicate is not None and duplicate.id != old_document_id:
            failed = self._failed(record, DUPLICATE_CONTENT, f"内容与《{duplicate.original_filename}》重复")
            self.storage.delete(record.storage_key)
            return failed
        record = self.repository.update_parse_result(
            record.id,
            text_sha256=text_sha256,
            page_count=page_count,
            parser_name=parser_name,
            parser_version=parser_version,
        ) or record

        current = self._transition(record, KnowledgeDocumentStatus.CHUNKING)
        if current is None:
            return self.repository.get_document(record.id) or record
        record = current
        chunks, page_ranges = self._prepare_chunks(text, record.original_filename)
        if not chunks:
            return self._failed(record, NO_EXTRACTABLE_TEXT, "文档没有可索引的正文")

        current = self._transition(record, KnowledgeDocumentStatus.EMBEDDING)
        if current is None:
            return self.repository.get_document(record.id) or record
        record = current
        try:
            embeddings: list[list[float]] = []
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                batch_embeddings = self.embedding_client.embed_texts(
                    [chunk.content for chunk in batch]
                )
                if len(batch_embeddings) != len(batch):
                    raise EmbeddingError("Embedding response count does not match chunk count")
                embeddings.extend(batch_embeddings)
            self.vector_repository.upsert_document_chunks(
                document_id=record.id,
                user_id=record.user_id,
                original_filename=record.original_filename,
                version_no=record.version_no,
                chunks=chunks,
                page_ranges=page_ranges,
                embeddings=embeddings,
            )
            vectors_written = True
        except Exception as exc:
            if vectors_written or _has_vectors(self.vector_repository, record.id):
                self._compensate_vectors(record.id)
            error_code = VECTOR_INDEX_FAILED if vectors_written else EMBEDDING_FAILED
            return self._failed(record, error_code, "文档向量化失败", exc)

        try:
            if old_document_id:
                self.vector_repository.delete_document(old_document_id)
                self.repository.soft_delete(old_document_id)
            record = self.repository.update_chunk_count(record.id, len(chunks)) or record
            ready = self._transition(record, KnowledgeDocumentStatus.READY)
            if ready is None:
                raise KnowledgeDocumentIngestionError("Document disappeared before READY update")
            return ready
        except Exception as exc:
            self._compensate_vectors(record.id)
            return self._failed(record, VECTOR_INDEX_FAILED, "文档索引状态更新失败", exc)

    def _extract(self, record: KnowledgeDocumentRecord) -> tuple[str, int | None, str, str]:
        path = self.storage.resolve(record.storage_key or "")
        if Path(record.original_filename).suffix.lower() == ".pdf":
            parsed = self.pdf_parser.parse(
                path,
                record.id,
                record.original_filename,
                self.settings.max_pages,
                self.settings.min_extracted_chars,
                self.settings.max_extracted_chars,
                self.settings.max_blocks_per_page,
            )
            return (
                parsed_pdf_to_markdown(parsed),
                parsed.page_count,
                getattr(self.pdf_parser, "name", "pymupdf"),
                getattr(self.pdf_parser, "version", "1"),
            )
        return path.read_text(encoding="utf-8"), None, "markdown", "1"

    @staticmethod
    def _prepare_chunks(text: str, source: str) -> tuple[list[KnowledgeChunk], list[tuple[int | None, int | None]]]:
        raw_chunks = chunk_markdown(text, source=source)
        prepared: list[KnowledgeChunk] = []
        ranges: list[tuple[int | None, int | None]] = []
        previous_page_end: int | None = None
        seen: set[str] = set()
        for chunk in raw_chunks:
            body, page_start, page_end = strip_page_sentinels(chunk.content)
            if page_start is None:
                page_start = previous_page_end
                page_end = previous_page_end
            if page_end is not None:
                previous_page_end = page_end
            if not body.strip():
                continue
            digest = sha256(body.encode("utf-8")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            prepared.append(replace(chunk, content=body, chunk_index=len(prepared)))
            ranges.append((page_start, page_end))
        return prepared, ranges

    def _transition(
        self,
        record: KnowledgeDocumentRecord,
        status: KnowledgeDocumentStatus,
    ) -> KnowledgeDocumentRecord | None:
        return self.repository.update_status(
            record.id,
            status,
            expected_status=record.status,
        )

    def _failed(
        self,
        record: KnowledgeDocumentRecord,
        error_code: str,
        message: str,
        cause: Exception | None = None,
    ) -> KnowledgeDocumentRecord:
        failed = self.repository.update_status(
            record.id,
            KnowledgeDocumentStatus.FAILED,
            error_code=error_code,
            error_message=message,
        )
        if failed is None:
            raise KnowledgeDocumentIngestionError("Document disappeared before FAILED update") from cause
        return failed

    def _compensate_vectors(self, document_id: str) -> None:
        self.vector_repository.delete_document(document_id)


def _has_vectors(vector_repository: Any, document_id: str) -> bool:
    try:
        return vector_repository.count_document(document_id) > 0
    except Exception:
        return True


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def ingest_document(user_id: str, original_filename: str, media_type: str, file_stream: BinaryIO):
    return KnowledgeDocumentIngestionService().ingest_document(
        user_id, original_filename, media_type, file_stream
    )


def reprocess_document(document_id: str):
    return KnowledgeDocumentIngestionService().reprocess_document(document_id)
