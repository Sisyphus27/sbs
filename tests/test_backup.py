import os
import sqlite3

import pytest

from webapp import db, backup


def test_snapshot_copies_db(tmp_path):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.close()
    bak = backup.snapshot(str(src), dest_dir=str(tmp_path / "bak"), week=2, ts="20260627T100000")
    assert os.path.exists(bak)
    # copied file is a valid sqlite db with settings table
    chk = sqlite3.connect(bak)
    assert chk.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
    chk.close()


def test_snapshot_filename_format(tmp_path):
    src = tmp_path / "sbs.db"
    db.connect(str(src)).close()  # creates empty file
    bak = backup.snapshot(str(src), dest_dir=str(tmp_path / "bak"), week=3, ts="t1")
    assert bak.endswith("sbs-w3-t1.db.bak")


def test_snapshot_rejects_missing_source(tmp_path):
    src = tmp_path / "missing.db"
    dest_dir = tmp_path / "bak"

    with pytest.raises(FileNotFoundError):
        backup.snapshot(str(src), dest_dir=str(dest_dir), week=1, ts="missing")

    assert not src.exists()
    assert list(dest_dir.iterdir()) == []


def test_snapshot_includes_committed_wal_data(tmp_path):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("UPDATE settings SET week = 7 WHERE id = 1")
    conn.commit()
    wal = tmp_path / "sbs.db-wal"
    assert wal.exists() and wal.stat().st_size > 0

    bak = backup.snapshot(
        str(src), dest_dir=str(tmp_path / "bak"), week=7, ts="wal"
    )

    with sqlite3.connect(bak) as chk:
        assert chk.execute("SELECT week FROM settings WHERE id = 1").fetchone()[0] == 7
    conn.close()


def test_snapshot_does_not_publish_failed_integrity_check(tmp_path, monkeypatch):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.close()
    dest_dir = tmp_path / "bak"
    dest_dir.mkdir()
    existing = dest_dir / "sbs-w1-existing.db.bak"
    existing.write_bytes(b"existing")

    def fail_integrity_check(_conn):
        raise RuntimeError("backup integrity check failed")

    monkeypatch.setattr(backup, "_integrity_check", fail_integrity_check)

    with pytest.raises(RuntimeError, match="integrity check failed"):
        backup.snapshot(str(src), dest_dir=str(dest_dir), week=1, ts="bad")

    assert set(dest_dir.iterdir()) == {existing}


def test_integrity_check_rejects_any_diagnostic_rows():
    class Result:
        def fetchall(self):
            return [("ok",), ("page 2 is never used",)]

    class Connection:
        def execute(self, sql):
            assert sql == "PRAGMA integrity_check"
            return Result()

    with pytest.raises(RuntimeError, match="page 2 is never used"):
        backup._integrity_check(Connection())


def test_snapshot_keeps_only_ten_most_recent_backups(tmp_path):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.close()
    dest_dir = tmp_path / "bak"
    dest_dir.mkdir()
    oldest = None
    for index in range(10):
        path = dest_dir / f"sbs-w1-old-{index}.db.bak"
        path.write_bytes(b"old")
        os.utime(path, (index + 1, index + 1))
        oldest = oldest or path

    newest = backup.snapshot(str(src), dest_dir=str(dest_dir), week=2, ts="new")

    retained = list(dest_dir.glob("sbs-w*.db.bak"))
    assert len(retained) == 10
    assert not oldest.exists()
    assert os.path.exists(newest)
