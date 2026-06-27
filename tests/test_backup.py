import sqlite3
from webapp import db, backup


def test_snapshot_copies_db(tmp_path):
    src = tmp_path / "sbs.db"
    conn = db.connect(str(src))
    db.init_schema(conn)
    conn.close()
    bak = backup.snapshot(str(src), dest_dir=str(tmp_path / "bak"), week=2, ts="20260627T100000")
    import os
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
