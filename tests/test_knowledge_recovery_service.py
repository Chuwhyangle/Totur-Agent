"""专项测试：知识文档启动恢复。"""

from types import SimpleNamespace

import app.services.knowledge_docs.recovery_service as recovery
from app.db.models import KnowledgeDocumentStatus


def record(document_id, status):
    return SimpleNamespace(id=document_id, status=status, storage_key=f"knowledge_docs/{document_id}.md")


def test_recovery_requeues_stuck_parsing_document(monkeypatch):
    records = [record("a", KnowledgeDocumentStatus.PARSING)]
    calls = []
    monkeypatch.setattr(recovery.repository, "list_non_terminal", lambda limit: records)
    service = SimpleNamespace(reprocess_document=lambda document_id: calls.append(document_id), vector_repository=None, storage=None)

    result = recovery.recover_pending_documents(ingestion_service=service)

    assert result == {"requeued": 1, "deleted": 0, "failed": 0}
    assert calls == ["a"]


def test_recovery_completes_stuck_deleting_document(monkeypatch):
    records = [record("a", KnowledgeDocumentStatus.DELETING)]
    deleted = []
    monkeypatch.setattr(recovery.repository, "list_non_terminal", lambda limit: records)
    monkeypatch.setattr(recovery.repository, "soft_delete", lambda document_id: deleted.append(document_id) or object())
    service = SimpleNamespace(
        vector_repository=SimpleNamespace(delete_document=lambda document_id: None),
        storage=SimpleNamespace(delete=lambda key: None),
    )

    result = recovery.recover_pending_documents(ingestion_service=SimpleNamespace(vector_repository=service.vector_repository, storage=service.storage), vector_repository=service.vector_repository, storage=service.storage)

    assert result == {"requeued": 0, "deleted": 1, "failed": 0}
    assert deleted == ["a"]


def test_recovery_continues_after_single_record_failure(monkeypatch):
    records = [record("a", KnowledgeDocumentStatus.PARSING), record("b", KnowledgeDocumentStatus.PARSING), record("c", KnowledgeDocumentStatus.PARSING)]
    calls = []
    monkeypatch.setattr(recovery.repository, "list_non_terminal", lambda limit: records)

    def reprocess(document_id):
        calls.append(document_id)
        if document_id == "b":
            raise RuntimeError("bad")

    result = recovery.recover_pending_documents(ingestion_service=SimpleNamespace(reprocess_document=reprocess, vector_repository=None, storage=None))

    assert calls == ["a", "b", "c"]
    assert result["requeued"] == 2
    assert result["failed"] == 1
