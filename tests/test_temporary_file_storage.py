"""Tests for safe temporary PDF filesystem storage and settings."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest

from app.services.documents.settings import (
    InvalidTemporaryDocumentSettings,
    TemporaryDocumentSettings,
    load_temporary_document_settings,
)
from app.services.documents.temporary_file_storage import (
    AttachmentStorageError,
    AttachmentTooLarge,
    InvalidAttachmentFilename,
    TemporaryFileStorage,
    UnsupportedAttachmentType,
)


PDF_BYTES = b"%PDF-1.7\nminimal-pdf-upload\n"


class TrackingStream(BytesIO):
    """Record requested read sizes to prove storage never performs read-all."""

    def __init__(self, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def make_storage(tmp_path: Path, chunk_bytes: int = 7) -> TemporaryFileStorage:
    return TemporaryFileStorage(tmp_path / "attachments", chunk_bytes)


def test_store_pdf_streams_fixed_size_chunks(tmp_path):
    storage = make_storage(tmp_path, chunk_bytes=7)
    stream = TrackingStream(PDF_BYTES * 3)

    stored = storage.store_pdf(stream, "notes.pdf", max_bytes=4096)

    assert len(stream.read_sizes) > 2
    assert set(stream.read_sizes) == {7}
    assert storage.resolve(stored.storage_key).read_bytes() == PDF_BYTES * 3


def test_store_pdf_uses_random_key_instead_of_original_filename(tmp_path):
    storage = make_storage(tmp_path)

    first = storage.store_pdf(BytesIO(PDF_BYTES), "private-resume.pdf", 4096)
    second = storage.store_pdf(BytesIO(PDF_BYTES), "private-resume.pdf", 4096)

    assert first.storage_key != second.storage_key
    assert "private-resume" not in first.storage_key
    assert first.storage_key.endswith(".pdf")
    UUID(first.storage_key.removesuffix(".pdf"))
    assert storage.resolve(first.storage_key).parent == storage.root_path


@pytest.mark.parametrize(
    "filename",
    [
        "../../evil.pdf",
        "folder/evil.pdf",
        r"..\evil.pdf",
        r"C:\temp\evil.pdf",
        "/tmp/evil.pdf",
    ],
)
def test_unsafe_original_filenames_are_rejected_without_path_escape(
    tmp_path,
    filename,
):
    storage = make_storage(tmp_path)

    with pytest.raises(InvalidAttachmentFilename):
        storage.store_pdf(BytesIO(PDF_BYTES), filename, 4096)

    assert list(tmp_path.rglob("*.pdf")) == []
    assert list(tmp_path.rglob("*.part")) == []


def test_uppercase_pdf_extension_is_accepted(tmp_path):
    storage = make_storage(tmp_path)

    stored = storage.store_pdf(BytesIO(PDF_BYTES), "NOTES.PDF", 4096)

    assert storage.exists(stored.storage_key)


def test_non_pdf_extension_is_rejected(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(UnsupportedAttachmentType, match=".pdf"):
        storage.store_pdf(BytesIO(PDF_BYTES), "notes.txt", 4096)


def test_non_pdf_mime_type_is_rejected(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(UnsupportedAttachmentType, match="recognizable PDF"):
        storage.store_pdf(
            BytesIO(PDF_BYTES),
            "notes.pdf",
            4096,
            mime_type="text/plain",
        )


def test_missing_pdf_magic_bytes_is_rejected_and_part_is_removed(tmp_path):
    storage = make_storage(tmp_path, chunk_bytes=2)

    with pytest.raises(UnsupportedAttachmentType, match="recognizable PDF"):
        storage.store_pdf(BytesIO(b"not-a-pdf"), "notes.pdf", 4096)

    assert list(tmp_path.rglob("*.pdf")) == []
    assert list(tmp_path.rglob("*.part")) == []


def test_empty_file_is_rejected(tmp_path):
    storage = make_storage(tmp_path)

    with pytest.raises(UnsupportedAttachmentType, match="recognizable PDF"):
        storage.store_pdf(BytesIO(b""), "notes.pdf", 4096)

    assert list(tmp_path.rglob("*.part")) == []


def test_actual_streamed_size_limit_is_enforced_and_part_is_removed(tmp_path):
    storage = make_storage(tmp_path, chunk_bytes=4)

    with pytest.raises(AttachmentTooLarge):
        storage.store_pdf(BytesIO(PDF_BYTES), "notes.pdf", max_bytes=8)

    assert list(tmp_path.rglob("*.pdf")) == []
    assert list(tmp_path.rglob("*.part")) == []


def test_store_pdf_returns_exact_size_and_sha256(tmp_path):
    storage = make_storage(tmp_path)

    stored = storage.store_pdf(BytesIO(PDF_BYTES), "notes.pdf", 4096)

    assert stored.size_bytes == len(PDF_BYTES)
    assert stored.sha256 == sha256(PDF_BYTES).hexdigest()
    assert storage.resolve(stored.storage_key).read_bytes() == PDF_BYTES


def test_delete_is_idempotent_for_missing_files(tmp_path):
    storage = make_storage(tmp_path)
    stored = storage.store_pdf(BytesIO(PDF_BYTES), "notes.pdf", 4096)

    storage.delete(stored.storage_key)
    storage.delete(stored.storage_key)

    assert storage.exists(stored.storage_key) is False


@pytest.mark.parametrize(
    "storage_key",
    [
        "../outside.pdf",
        "nested/../../outside.pdf",
        r"..\outside.pdf",
        r"C:\outside.pdf",
        "/outside.pdf",
        "",
    ],
)
def test_resolve_rejects_storage_key_path_escape(tmp_path, storage_key):
    storage = make_storage(tmp_path)

    with pytest.raises(AttachmentStorageError):
        storage.resolve(storage_key)


def test_settings_resolve_relative_root_without_creating_it(tmp_path):
    settings = load_temporary_document_settings(
        environment={
            "TEMP_DOCUMENT_ROOT": "local/attachments",
            "TEMP_DOCUMENT_MAX_BYTES": "4096",
            "TEMP_DOCUMENT_TTL_HOURS": "12",
            "TEMP_DOCUMENT_MAX_FILES_PER_SESSION": "3",
            "TEMP_DOCUMENT_WRITE_CHUNK_BYTES": "2048",
        },
        project_root=tmp_path,
    )

    assert settings.root_path == (tmp_path / "local/attachments").resolve()
    assert settings.max_bytes == 4096
    assert settings.ttl_hours == 12
    assert settings.max_files_per_session == 3
    assert settings.write_chunk_bytes == 2048
    assert settings.root_path.exists() is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TEMP_DOCUMENT_MAX_BYTES", "not-an-int"),
        ("TEMP_DOCUMENT_MAX_BYTES", "1023"),
        ("TEMP_DOCUMENT_TTL_HOURS", "0"),
        ("TEMP_DOCUMENT_MAX_FILES_PER_SESSION", "0"),
        ("TEMP_DOCUMENT_WRITE_CHUNK_BYTES", "0"),
    ],
)
def test_invalid_numeric_settings_are_rejected(tmp_path, name, value):
    with pytest.raises(InvalidTemporaryDocumentSettings):
        load_temporary_document_settings(
            environment={name: value},
            project_root=tmp_path,
        )


def test_injected_settings_validate_values_without_creating_root(tmp_path):
    root = tmp_path / "not-created"

    settings = TemporaryDocumentSettings(root_path=root)

    assert settings.root_path == root.resolve()
    assert root.exists() is False
