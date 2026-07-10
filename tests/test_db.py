import sqlite3
from webapp import db


def test_init_schema_creates_tables_and_default_settings(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"settings", "lifts", "lift_state", "history"} <= tables
    assert "sbs_schedule" in tables                       # Task 5: schedule table
    s = conn.execute("SELECT * FROM settings").fetchone()
    assert s["week"] == 1 and s["days_per_week"] == 4 and s["rounding"] == 2.5
    assert s["incr"] == 2.5 and s["t2_reset_pct"] == 0.75 and s["t2_fail"] == 3 and s["t3_target"] == 15
    conn.close()


def test_init_schema_seeds_schedule_when_empty(tmp_path):
    """init_schema seeds sbs_schedule from DEFAULT_SCHEDULE exactly once (Task 5)."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    n = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
    assert n == 42                                        # 21 main + 21 aux
    # re-running init_schema must NOT re-seed (idempotent)
    db.init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0] == 42
    conn.close()


def test_init_schema_has_lift_kind_reseeded_cycle_and_incr_columns(tmp_path):
    """lifts.lift_kind + lifts.incr and lift_state.reseeded_cycle exist (Task 5 / per-lift incr)."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lift_cols = {r[1] for r in conn.execute("PRAGMA table_info(lifts)").fetchall()}
    state_cols = {r[1] for r in conn.execute("PRAGMA table_info(lift_state)").fetchall()}
    assert "lift_kind" in lift_cols
    assert "incr" in lift_cols          # per-lift t2/t3 progression step (nullable)
    assert "reseeded_cycle" in state_cols
    # reseeded_cycle defaults to 0 so advance_week's UPSERT won't NULL it out
    conn.execute(
        "INSERT INTO lifts (name, tier, day, sort_order, sets, max) "
        "VALUES ('Squat', 'sbs', 1, 0, 5, 100.0)"
    )
    conn.execute(
        "INSERT INTO lift_state (lift_id, tier, tm) VALUES (1, 'sbs', 100.0)"
    )
    rc = conn.execute(
        "SELECT reseeded_cycle FROM lift_state WHERE lift_id = 1"
    ).fetchone()[0]
    assert rc == 0
    conn.close()


def test_foreign_keys_enforced(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()
