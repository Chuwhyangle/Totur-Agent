"""Service and API tests for temporary conversation PDF attachments."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes.attachments import get_temporary_document_service
from app.db import database
from app.db.models import DocumentStatus
from app.main import app
from app.repositories.document_repository import (
    create_attachment_document,
    get_document,
    update_document_status,
)
from app.repositories.session_repository import create_session
import app.services.documents.temporary_document_service as document_service_module
from app.services.documents.settings import TemporaryDocumentSettings
from app.services.documents.temporary_document_service import (
    AttachmentCleanupError,
    AttachmentCreationError,
    AttachmentLimitExceeded,
    AttachmentNotFoundError,
    TemporaryDocumentService,
)
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    TemporaryFileStorage,
)


PDF_BYTES = b"%PDF-1.7\ntemporary attachment\n"


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "attachments.db")


def make_service(
    tmp_path,
    *,
    max_bytes=4096,
    max_files=5,
    now_provider=None,
):
    settings = TemporaryDocumentSettings(
        root_path=tmp_path / "attachment-files",
        max_bytes=max_bytes,
        ttl_hours=24,
        max_files_per_session=max_files,
        write_chunk_bytes=1024,
    )
    return TemporaryDocumentService(
        settings=settings,
        now_provider=now_provider,
    )


def make_upload(
    content=PDF_BYTES,
    filename="notes.pdf",
    content_type="application/pdf",
):
    return SimpleNamespace(
        file=BytesIO(content),
        filename=filename,
        content_type=content_type,
    )


@contextmanager
def api_client_for(service):
    app.dependency_overrides[get_temporary_document_service] = lambda: service
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_temporary_document_service, None)


def test_owner_can_create_uploaded_attachment(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    record = service.create_attachment("alice", session.id, make_upload())

    assert record.user_id == "alice"
    assert record.session_id == session.id
    assert record.status is DocumentStatus.UPLOADED
    assert record.size_bytes == len(PDF_BYTES)
    assert record.content_hash == f"sha256:{sha256(PDF_BYTES).hexdigest()}"
    assert record.storage_path != "notes.pdf"
    assert service.storage.resolve(record.storage_path).read_bytes() == PDF_BYTES
    assert record.expires_at > record.created_at


def test_other_user_cannot_upload_to_session(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    with pytest.raises(AttachmentNotFoundError):
        service.create_attachment("bob", session.id, make_upload())

    assert service.settings.root_path.exists() is False


def test_attachment_limit_rejects_additional_upload(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path, max_files=1)
    service.create_attachment("alice", session.id, make_upload(filename="one.pdf"))

    with pytest.raises(AttachmentLimitExceeded):
        service.create_attachment("alice", session.id, make_upload(filename="two.pdf"))

    assert len(list(service.settings.root_path.glob("*.pdf"))) == 1


def test_database_failure_compensates_by_deleting_stored_file(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    def fail_create_document(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        document_service_module,
        "create_attachment_document",
        fail_create_document,
    )

    with pytest.raises(AttachmentCreationError):
        service.create_attachment("alice", session.id, make_upload())

    assert list(service.settings.root_path.glob("*.pdf")) == []
    assert list(service.settings.root_path.glob("*.part")) == []


def test_delete_attachment_removes_file_and_purges_metadata(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())
    stored_path = service.storage.resolve(record.storage_path)

    service.delete_attachment(record.id, "alice", session.id)

    assert stored_path.exists() is False
    assert get_document(record.id) is None


def test_delete_attachment_removes_future_parsed_artifact(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())
    original_path = service.storage.resolve(record.storage_path)
    parsed_key = "parsed-result.json"
    parsed_path = service.storage.resolve(parsed_key)
    parsed_path.write_text("{}", encoding="utf-8")
    update_document_status(record.id, DocumentStatus.PARSING)
    update_document_status(
        record.id,
        DocumentStatus.READY,
        parsed_path=parsed_key,
        page_count=1,
    )

    service.delete_attachment(record.id, "alice", session.id)

    assert original_path.exists() is False
    assert parsed_path.exists() is False
    assert get_document(record.id) is None

def test_delete_attachment_succeeds_when_file_is_already_missing(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())
    service.storage.delete(record.storage_path)

    service.delete_attachment(record.id, "alice", session.id)

    assert get_document(record.id) is None


def test_file_delete_failure_leaves_document_in_deleting(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())

    def fail_delete(_storage_key):
        raise AttachmentStorageError("simulated delete failure")

    monkeypatch.setattr(service.storage, "delete", fail_delete)

    with pytest.raises(AttachmentCleanupError):
        service.delete_attachment(record.id, "alice", session.id)

    retained = get_document(record.id)
    assert retained is not None
    assert retained.status is DocumentStatus.DELETING


def test_unauthorized_delete_preserves_file_and_metadata(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())
    stored_path = service.storage.resolve(record.storage_path)

    with pytest.raises(AttachmentNotFoundError):
        service.delete_attachment(record.id, "bob", session.id)

    assert stored_path.exists()
    assert get_document(record.id).status is DocumentStatus.UPLOADED


def test_post_attachment_returns_201_and_safe_dto(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    with api_client_for(service) as client:
        response = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "alice"},
            files={"file": ("Resume.PDF", PDF_BYTES, "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "Resume.PDF"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["status"] == "UPLOADED"
    assert {
        "storage_path",
        "parsed_path",
        "content_hash",
        "user_id",
    }.isdisjoint(body)


def test_list_api_returns_only_owned_session_unexpired_attachments(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    base_now = datetime.now(timezone.utc)
    alice_session = create_session("alice")
    other_alice_session = create_session("alice")
    bob_session = create_session("bob")
    creator = make_service(tmp_path, now_provider=lambda: base_now)
    visible = creator.create_attachment(
        "alice",
        alice_session.id,
        make_upload(filename="visible.pdf"),
    )
    creator.create_attachment(
        "alice",
        other_alice_session.id,
        make_upload(filename="other-session.pdf"),
    )
    creator.create_attachment(
        "bob",
        bob_session.id,
        make_upload(filename="other-user.pdf"),
    )
    create_attachment_document(
        user_id="alice",
        session_id=alice_session.id,
        original_filename="expired.pdf",
        mime_type="application/pdf",
        size_bytes=len(PDF_BYTES),
        storage_path="expired.pdf",
        expires_at=base_now + timedelta(hours=1),
    )
    reader = make_service(
        tmp_path,
        now_provider=lambda: base_now + timedelta(hours=2),
    )

    with api_client_for(reader) as client:
        response = client.get(
            f"/sessions/{alice_session.id}/attachments",
            params={"user_id": "alice"},
        )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [visible.id]


def test_get_attachment_api_enforces_user_and_session_ownership(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    other_session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())

    with api_client_for(service) as client:
        owner_response = client.get(
            f"/sessions/{session.id}/attachments/{record.id}",
            params={"user_id": "alice"},
        )
        other_user_response = client.get(
            f"/sessions/{session.id}/attachments/{record.id}",
            params={"user_id": "bob"},
        )
        other_session_response = client.get(
            f"/sessions/{other_session.id}/attachments/{record.id}",
            params={"user_id": "alice"},
        )

    assert owner_response.status_code == 200
    assert other_user_response.status_code == 404
    assert other_session_response.status_code == 404


def test_delete_attachment_api_returns_204(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())

    with api_client_for(service) as client:
        response = client.delete(
            f"/sessions/{session.id}/attachments/{record.id}",
            params={"user_id": "alice"},
        )

    assert response.status_code == 204
    assert response.content == b""
    assert get_document(record.id) is None


def test_unauthorized_delete_api_returns_404_without_side_effects(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)
    record = service.create_attachment("alice", session.id, make_upload())
    stored_path = service.storage.resolve(record.storage_path)

    with api_client_for(service) as client:
        response = client.delete(
            f"/sessions/{session.id}/attachments/{record.id}",
            params={"user_id": "bob"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "attachment_not_found"
    assert stored_path.exists()
    assert get_document(record.id) is not None


def test_upload_to_missing_or_unowned_session_returns_404(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    with api_client_for(service) as client:
        missing = client.post(
            "/sessions/999999/attachments",
            data={"user_id": "alice"},
            files={"file": ("notes.pdf", PDF_BYTES, "application/pdf")},
        )
        unowned = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "bob"},
            files={"file": ("notes.pdf", PDF_BYTES, "application/pdf")},
        )

    assert missing.status_code == 404
    assert unowned.status_code == 404


def test_oversized_upload_returns_413(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path, max_bytes=1024)
    oversized = b"%PDF-" + (b"x" * 1024)

    with api_client_for(service) as client:
        response = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "alice"},
            files={"file": ("large.pdf", oversized, "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "attachment_too_large"
    assert list(service.settings.root_path.glob("*.part")) == []


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("notes.txt", PDF_BYTES, "application/pdf"),
        ("notes.pdf", PDF_BYTES, "text/plain"),
        ("notes.pdf", b"not-a-pdf", "application/pdf"),
    ],
)
def test_unsupported_upload_returns_415(
    monkeypatch,
    tmp_path,
    filename,
    content,
    content_type,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    with api_client_for(service) as client:
        response = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "alice"},
            files={"file": (filename, content, content_type)},
        )

    assert response.status_code == 415
    assert response.json()["detail"]["error"] == "unsupported_attachment_type"


def test_attachment_limit_api_returns_409(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path, max_files=1)
    service.create_attachment("alice", session.id, make_upload())

    with api_client_for(service) as client:
        response = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "alice"},
            files={"file": ("second.pdf", PDF_BYTES, "application/pdf")},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "attachment_limit_reached"


def test_storage_failure_api_returns_stable_500_without_path_details(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    session = create_session("alice")
    service = make_service(tmp_path)

    def fail_store(*_args, **_kwargs):
        raise AttachmentStorageError(r"failed at C:\secret\attachment.pdf")

    monkeypatch.setattr(service.storage, "store_pdf", fail_store)

    with api_client_for(service) as client:
        response = client.post(
            f"/sessions/{session.id}/attachments",
            data={"user_id": "alice"},
            files={"file": ("notes.pdf", PDF_BYTES, "application/pdf")},
        )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "attachment_storage_error"
    assert "secret" not in response.text


def test_attachment_routes_are_registered():
    paths = app.openapi()["paths"]

    assert {"get", "post"}.issubset(
        paths["/sessions/{session_id}/attachments"]
    )
    assert {"get", "delete"}.issubset(
        paths["/sessions/{session_id}/attachments/{attachment_id}"]
    )


