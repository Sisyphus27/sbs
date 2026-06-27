import sqlite3
from webapp import db


def test_init_schema_creates_tables_and_default_settings(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"settings", "lifts", "lift_state", "history"} <= tables
    s = conn.execute("SELECT * FROM settings").fetchone()
    assert s["week"] == 1 and s["days_per_week"] == 4 and s["rounding"] == 2.5
    assert s["incr"] == 2.5 and s["t2_reset_pct"] == 0.7 and s["t2_fail"] == 3 and s["t3_target"] == 15
    conn.close()


def test_foreign_keys_enforced(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()
