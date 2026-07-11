import sqlite3
from webapp import db


def _legacy_db(tmp_path):
    """Build a lifts table WITHOUT the incr column, mirroring a pre-migration DB."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK (id=1), week INTEGER NOT NULL,
            days_per_week INTEGER NOT NULL, rounding REAL NOT NULL, incr REAL NOT NULL,
            t2_reset_pct REAL NOT NULL, t2_fail INTEGER NOT NULL, t3_target INTEGER NOT NULL);
        INSERT INTO settings VALUES (1, 1, 4, 2.5, 2.5, 0.75, 3, 15);
        CREATE TABLE lifts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            tier TEXT NOT NULL, day INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            sets INTEGER NOT NULL DEFAULT 3, max REAL, intensity REAL, reps INTEGER,
            repout INTEGER, start REAL, lift_kind TEXT);
        CREATE TABLE lift_state (lift_id INTEGER PRIMARY KEY, tier TEXT NOT NULL, tm REAL,
            weight REAL, target INTEGER, streak INTEGER NOT NULL DEFAULT 0, est1rm REAL,
            reseeded_cycle INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, lift_id INTEGER NOT NULL,
            week INTEGER NOT NULL, weight REAL NOT NULL, reps INTEGER NOT NULL, ts TEXT NOT NULL);
        CREATE TABLE week_log (lift_id INTEGER NOT NULL, week INTEGER NOT NULL, reps INTEGER NOT NULL,
            PRIMARY KEY (lift_id, week));
        CREATE TABLE sbs_schedule (kind TEXT NOT NULL, week INTEGER NOT NULL, intensity REAL NOT NULL,
            reps INTEGER NOT NULL, repout INTEGER NOT NULL, PRIMARY KEY (kind, week));
        INSERT INTO lifts (name, tier, day, sets, start) VALUES ('Rows', 't2', 1, 4, 85.0);
    """)
    conn.commit()
    conn.close()
    return path


def _has_incr(conn):
    return any(r[1] == "incr" for r in conn.execute("PRAGMA table_info(lifts)"))


def test_migrate_adds_incr_column(tmp_path, monkeypatch):
    path = _legacy_db(tmp_path)
    import migrate_incr
    monkeypatch.chdir(tmp_path)
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    # existing rows keep NULL incr (inherit global)
    row = conn.execute("SELECT incr FROM lifts WHERE name='Rows'").fetchone()
    assert row[0] is None
    conn.close()


def test_migrate_idempotent_on_already_migrated(tmp_path, monkeypatch):
    path = _legacy_db(tmp_path)
    import migrate_incr
    monkeypatch.chdir(tmp_path)
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))  # second run no-op
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    conn.close()


def test_migrate_idempotent_on_fresh_schema(tmp_path, monkeypatch):
    # a DB created by init_schema already has incr -> migrate is a no-op
    path = str(tmp_path / "fresh.db")
    conn = db.connect(path)
    db.init_schema(conn)
    conn.close()
    import migrate_incr
    migrate_incr.main(db_path=path, backup_dir=str(tmp_path / "bak"))
    conn = sqlite3.connect(path)
    assert _has_incr(conn)
    conn.close()
