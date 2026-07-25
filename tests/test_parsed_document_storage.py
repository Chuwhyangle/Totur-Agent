"""Tests for atomic UTF-8 structured parsing result storage."""

import os

import pytest

import app.services.documents.parsed_document_storage as storage_module
from app.services.documents.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedTextBlock,
)
from app.services.documents.parsed_document_storage import (
    ParsedDocumentStorage,
    ParsedDocumentStorageError,
)
from app.services.documents.temporary_file_storage import TemporaryFileStorage


def make_storage(tmp_path):
    files = TemporaryFileStorage(tmp_path / "attachments", 1024)
    return ParsedDocumentStorage(files)


def make_document():
    return ParsedDocument(
        schema_version=1,
        document_id="2e4d8b95-7ea3-4ea3-9c03-57ecdd906871",
        original_filename="private-resume.pdf",
        page_count=1,
        extracted_char_count=6,
        pages=(
            ParsedPage(
                page_number=1,
                width=595.0,
                height=842.0,
                blocks=(
                    ParsedTextBlock(
                        block_index=0,
                        text="中文内容",
                        bbox=(72.0, 80.0, 500.0, 120.0),
                    ),
                ),
            ),
        ),
    )


def test_json_is_written_atomically_and_can_be_read(tmp_path):
    storage = make_storage(tmp_path)

    key = storage.write_json(make_document().document_id, make_document())

    assert key == "parsed/2e4d8b95-7ea3-4ea3-9c03-57ecdd906871.json"
    assert storage.exists(key)
    assert list(tmp_path.rglob("*.part")) == []
    assert storage.read_json(key)["schema_version"] == 1


def test_json_uses_utf8_and_preserves_chinese(tmp_path):
    storage = make_storage(tmp_path)

    key = storage.write_json(make_document().document_id, make_document())
    raw_text = storage.file_storage.resolve(key).read_text(encoding="utf-8")

    assert "中文内容" in raw_text
    assert r"\u4e2d" not in raw_text
    assert storage.read_json(key)["pages"][0]["blocks"][0]["text"] == "中文内容"


def test_storage_key_never_contains_original_filename_or_absolute_path(tmp_path):
    storage = make_storage(tmp_path)
    document = make_document()

    key = storage.write_json(document.document_id, document)

    assert document.original_filename not in key
    assert not os.path.isabs(key)
    assert storage.file_storage.resolve(key).is_relative_to(
        storage.file_storage.root_path
    )


@pytest.mark.parametrize(
    "storage_key",
    ["../outside.json", "parsed/../../outside.json", r"C:\outside.json", "/outside.json"],
)
def test_read_and_delete_reject_path_escape(tmp_path, storage_key):
    storage = make_storage(tmp_path)

    with pytest.raises(ParsedDocumentStorageError):
        storage.read_json(storage_key)
    with pytest.raises(ParsedDocumentStorageError):
        storage.delete(storage_key)


def test_write_failure_removes_part_file(monkeypatch, tmp_path):
    storage = make_storage(tmp_path)

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(storage_module.os, "replace", fail_replace)

    with pytest.raises(ParsedDocumentStorageError):
        storage.write_json(make_document().document_id, make_document())

    assert list(tmp_path.rglob("*.part")) == []
    assert list(tmp_path.rglob("*.json")) == []


def test_delete_is_idempotent(tmp_path):
    storage = make_storage(tmp_path)
    key = storage.write_json(make_document().document_id, make_document())

    storage.delete(key)
    storage.delete(key)

    assert storage.exists(key) is False
