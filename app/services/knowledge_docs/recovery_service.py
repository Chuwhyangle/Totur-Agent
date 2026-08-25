"""Startup recovery for durable knowledge-document processing."""

from __future__ import annotations

import logging
from typing import Any

import app.repositories.knowledge_document_repository as repository
from app.db.models import KnowledgeDocumentStatus
from app.services.knowledge_docs.ingestion_service import (
    KnowledgeDocumentIngestionService,
)


logger = logging.getLogger(__name__)


def recover_pending_documents(
    limit: int = 100,
    *,
    ingestion_service: Any | None = None,
    vector_repository: Any | None = None,
    storage: Any | None = None,
) -> dict[str, int]:
    """Retry non-terminal records because BackgroundTasks do not survive restart."""

    service = ingestion_service or KnowledgeDocumentIngestionService()
    vector_repository = vector_repository or service.vector_repository
    storage = storage or service.storage
    stats = {"requeued": 0, "deleted": 0, "failed": 0}
    for record in repository.list_non_terminal(limit):
        try:
            if record.status is KnowledgeDocumentStatus.DELETING:
                vector_repository.delete_document(record.id)
                storage.delete(record.storage_key)
                deleted = repository.soft_delete(record.id)
                if deleted is not None:
                    stats["deleted"] += 1
            else:
                service.reprocess_document(record.id)
                stats["requeued"] += 1
        except Exception:
            stats["failed"] += 1
            logger.exception("knowledge_document_recovery_failed document_id=%s", record.id)
    return stats
