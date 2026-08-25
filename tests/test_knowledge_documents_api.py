"""专项测试：知识文档 API。"""

from io import BytesIO

from fastapi.testclient import TestClient

import app.main as main_module
import app.api.routes.knowledge_documents as knowledge_route
from app.db.models import KnowledgeDocumentStatus
import app.repositories.knowledge_document_repository as repository
from app.services.knowledge_docs.ingestion_service import KnowledgeDocumentIngestionService
from app.services.knowledge_docs.storage import KnowledgeDocumentStorage


class FakeVector:
    def __init__(self):
        self.ids = set()
        self.fail_delete = False

    def delete_document(self, document_id):
        if self.fail_delete:
            raise RuntimeError("vector down")
        self.ids.discard(document_id)

    def upsert_document_chunks(self, **kwargs):
        self.ids.add(kwargs["document_id"])
        return len(kwargs["chunks"])


class FakeService:
    def __init__(self, tmp_path):
        self.vector_repository = FakeVector()
        self.storage = KnowledgeDocumentStorage(tmp_path)
        self.real = KnowledgeDocumentIngestionService(
            repository=repository,
            vector_repository=self.vector_repository,
            storage=self.storage,
            embedding_client=type("Embedding", (), {"embed_texts": lambda _, texts: [[1.0, 0.0] for _ in texts]})(),
        )

    def ingest_document(self, **kwargs):
        return self.real.ingest_document(**kwargs)

    def reprocess_document(self, document_id):
        return self.real.reprocess_document(document_id)


def test_upload_returns_202_and_enqueues(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/knowledge/documents",
            data={"user_id": "alice"},
            files={"file": ("notes.md", b"# Notes\n\nbody", "text/markdown")},
        )

    assert response.status_code == 202
    assert response.json()["document"]["status"] == "READY"


def test_duplicate_upload_returns_200_with_duplicate_flag(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)

    with TestClient(main_module.app) as client:
        payload = {"user_id": "alice"}
        files = {"file": ("notes.md", b"same", "text/markdown")}
        assert client.post("/knowledge/documents", data=payload, files=files).status_code == 202
        response = client.post("/knowledge/documents", data=payload, files=files)

    assert response.status_code == 200
    assert response.json()["duplicate"] is True


def test_list_filters_by_status_and_respects_limit(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)
    service.real.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"alpha body"))
    service.real.ingest_document("alice", "b.md", "text/markdown", BytesIO(b"beta body"))

    with TestClient(main_module.app) as client:
        response = client.get("/knowledge/documents", params={"user_id": "alice", "status": "READY", "limit": 1})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_get_single_document_returns_user_safe_message_on_failure(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)
    record, _ = service.real.ingest_document("alice", "bad.md", "text/markdown", BytesIO(b"\xff"))

    with TestClient(main_module.app) as client:
        response = client.get(f"/knowledge/documents/{record.id}", params={"user_id": "alice"})

    assert response.status_code == 200
    assert response.json()["user_safe_message"]


def test_delete_cascades_to_vectors_and_storage(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)
    record, _ = service.real.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"a"))
    path = service.storage.resolve(record.storage_key)
    assert path.exists()

    with TestClient(main_module.app) as client:
        response = client.delete(f"/knowledge/documents/{record.id}", params={"user_id": "alice"})

    assert response.status_code == 200
    assert response.json()["status"] == "DELETED"
    assert not path.exists()


def test_delete_stops_at_deleting_when_vector_delete_fails(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)
    record, _ = service.real.ingest_document("alice", "a.md", "text/markdown", BytesIO(b"a"))
    service.vector_repository.fail_delete = True

    with TestClient(main_module.app, raise_server_exceptions=False) as client:
        response = client.delete(f"/knowledge/documents/{record.id}", params={"user_id": "alice"})

    assert response.status_code == 500
    assert repository.get_document(record.id).status is KnowledgeDocumentStatus.DELETING


def test_retry_uses_cas_and_rejects_when_already_processing(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)
    record, _ = service.real.ingest_document("alice", "bad.md", "text/markdown", BytesIO(b"\xff"))
    service.real.reprocess_document = lambda document_id: repository.get_document(document_id)

    with TestClient(main_module.app) as client:
        first = client.post(f"/knowledge/documents/{record.id}/retry", params={"user_id": "alice"})
        second = client.post(f"/knowledge/documents/{record.id}/retry", params={"user_id": "alice"})

    assert first.status_code == 202
    assert second.status_code == 409


def test_unsupported_extension_returns_415(tmp_path, monkeypatch):
    service = FakeService(tmp_path)
    monkeypatch.setattr(knowledge_route, "get_knowledge_ingestion_service", lambda: service)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/knowledge/documents",
            data={"user_id": "alice"},
            files={"file": ("notes.txt", b"bad", "text/plain")},
        )

    assert response.status_code == 415
