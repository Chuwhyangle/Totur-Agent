"""Backup script tests using only temporary source and destination directories."""

import os
import sqlite3
import tarfile
import time

import pytest

from scripts import backup


def _create_sqlite(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        connection.execute("INSERT INTO notes (body) VALUES ('safe backup')")
        connection.commit()
    finally:
        connection.close()


def test_run_backup_creates_readable_sqlite_and_chroma_archive(tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "archives"
    data_dir.mkdir()
    _create_sqlite(data_dir / "tutor_agent.db")
    (data_dir / "chroma_db" / "segments").mkdir(parents=True)
    (data_dir / "chroma_db" / "chroma.sqlite3").write_bytes(b"chroma")
    (data_dir / "chroma_db" / "segments" / "index.bin").write_bytes(b"index")

    archive = backup.run_backup(data_dir, backup_dir, keep=7)

    assert archive.parent == backup_dir
    assert archive.is_file()
    extract_dir = tmp_path / "extract"
    with tarfile.open(archive, "r:gz") as package:
        package.extractall(extract_dir)
        assert sorted(package.getnames()) == [
            "chroma_db",
            "chroma_db/chroma.sqlite3",
            "chroma_db/segments",
            "chroma_db/segments/index.bin",
            "tutor_agent.db",
        ]

    connection = sqlite3.connect(extract_dir / "tutor_agent.db")
    try:
        assert connection.execute("SELECT body FROM notes").fetchone() == ("safe backup",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()


def test_cleanup_keeps_newest_backups_and_does_not_touch_outside_files(tmp_path):
    backup_dir = tmp_path / "archives"
    outside_dir = tmp_path / "outside"
    backup_dir.mkdir()
    outside_dir.mkdir()
    backups = []
    for index in range(4):
        path = backup_dir / f"backup_20260728_00000{index}.tar.gz"
        path.write_bytes(str(index).encode())
        timestamp = time.time() - (10 - index)
        os.utime(path, (timestamp, timestamp))
        backups.append(path)
    unrelated_inside = backup_dir / "manual-export.tar.gz"
    unrelated_inside.write_bytes(b"manual")
    outside = outside_dir / "backup_20200101_000000.tar.gz"
    outside.write_bytes(b"outside")

    backup._cleanup_old_backups(backup_dir, keep=2)

    assert [path.exists() for path in backups] == [False, False, True, True]
    assert unrelated_inside.exists()
    assert outside.exists()


@pytest.mark.xfail(strict=True, reason="scripts/backup.py currently omits corpus and attachment directories")
def test_archive_includes_corpus_and_attachment_directories(tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "archives"
    data_dir.mkdir()
    _create_sqlite(data_dir / "tutor_agent.db")
    (data_dir / "corpus").mkdir()
    (data_dir / "corpus" / "lesson.md").write_text("lesson", encoding="utf-8")
    (data_dir / "attachments").mkdir()
    (data_dir / "attachments" / "resume.pdf").write_bytes(b"pdf")

    archive = backup.run_backup(data_dir, backup_dir, keep=7)

    with tarfile.open(archive, "r:gz") as package:
        names = set(package.getnames())
    assert "corpus/lesson.md" in names
    assert "attachments/resume.pdf" in names


@pytest.mark.xfail(strict=True, reason="missing SQLite and Chroma sources currently produce an empty successful archive")
def test_missing_all_data_sources_has_clear_error_classification(tmp_path):
    data_dir = tmp_path / "empty-data"
    data_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="SQLite|Chroma|data source"):
        backup.run_backup(data_dir, tmp_path / "archives", keep=7)


def test_missing_data_sources_are_reported_as_warnings_without_touching_real_paths(tmp_path, capsys):
    archive = backup.run_backup(tmp_path / "empty-data", tmp_path / "archives", keep=7)
    output = capsys.readouterr().out
    assert archive.is_file()
    assert "数据库文件不存在" in output
    assert "ChromaDB 目录不存在" in output
