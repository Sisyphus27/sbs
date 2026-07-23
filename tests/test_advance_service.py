import sqlite3
from webapp import db, repo
from webapp.services import advance


def _seed(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    ids = {}
    ids["Squat"] = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                                    day=1, sort_order=0,
                                    sets=5, max=135.0, intensity=0.7, reps=5, repout=10,
                                    start=None, lift_kind="main")
    ids["Rows"] = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                                   day=1, sort_order=1,
                                   sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    ids["Curl"] = repo.create_lift(conn, name="Curl", load_model="barbell", mode="linear_t3",
                                   day=1, sort_order=2,
                                   sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    return conn, ids


def test_advance_week_runs_engine_and_bumps_week(tmp_path):
    conn, ids = _seed(tmp_path)
    new_week = advance.advance_week(conn, {ids["Squat"]: 13, ids["Rows"]: 10, ids["Curl"]: 15})
    assert new_week == 2
    assert repo.get_settings(conn)["week"] == 2
    # Squat beat repout(10) by 3 -> +1.5% -> tm 135*1.015=137.025 (raw, no MROUND)
    squat_id = ids["Squat"]
    st = repo.get_lift_state(conn, squat_id)
    assert st["tm"] == 137.025
    # history appended for logged lift
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_advance_week_skips_unlogged_lifts(tmp_path):
    conn, ids = _seed(tmp_path)
    advance.advance_week(conn, {ids["Squat"]: 10})  # Rows/Curl not logged
    curl_id = ids["Curl"]
    assert repo.list_history(conn, curl_id) == []   # no history
    assert repo.get_lift_state(conn, curl_id)["weight"] == 40.0  # unchanged
    conn.close()


def test_advance_week_rows_t2_hit_increments(tmp_path):
    conn, ids = _seed(tmp_path)
    advance.advance_week(conn, {ids["Rows"]: 10})  # reps 10 >= target 8 -> hit -> +incr 2.5
    rows_id = ids["Rows"]
    assert repo.get_lift_state(conn, rows_id)["weight"] == 87.5
    conn.close()


def test_advance_week_handles_duplicate_names_per_day(tmp_path):
    """Same exercise on two days is two independent rows; logging by id targets each."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    d1 = repo.create_lift(conn, name="Face Pull", load_model="barbell", mode="linear_t3",
                          day=2, sort_order=0,
                          sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
    d4 = repo.create_lift(conn, name="Face Pull", load_model="barbell", mode="linear_t3",
                          day=4, sort_order=0,
                          sets=3, max=None, intensity=None, reps=None, repout=None, start=45.0)
    advance.advance_week(conn, {d1: 20, d4: 12})  # d1 hit (+2.5), d4 missed (unchanged)
    assert repo.get_lift_state(conn, d1)["weight"] == 32.5
    assert repo.get_lift_state(conn, d4)["weight"] == 45.0
    conn.close()


def test_lift_from_row_tolerates_missing_incr_column():
    """Regression: legacy DBs that predate the lifts.incr column (pre-migrate_incr)
    must not blow up _lift_from_row with IndexError. A row lacking incr should
    yield a Lift with incr=None (inherit global), per ADR 0003 / design D1.

    Mirrors the legacy-DB shape: lift_kind column present (added by Task 5
    migration before replay) but incr column absent (added by separate
    migrate_incr.py which the legacy DB has not yet run).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE lifts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            load_model TEXT NOT NULL,
            mode       TEXT NOT NULL,
            day        INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            sets       INTEGER NOT NULL DEFAULT 3,
            max        REAL,
            intensity  REAL,
            reps       INTEGER,
            repout     INTEGER,
            start      REAL,
            lift_kind  TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO lifts (name, load_model, mode, day, max, intensity, reps, repout, sets, start, lift_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Rows", "barbell", "linear_t2", 1, None, None, None, None, 3, 85.0, "main"),
    )
    row = conn.execute("SELECT * FROM lifts WHERE name = 'Rows'").fetchone()
    conn.close()

    lift = advance._lift_from_row(row)
    assert lift.name == "Rows"
    assert lift.incr is None  # no IndexError; inherits global


def test_lift_from_row_maps_bodyweight_pct_and_progression(tmp_path):
    """_lift_from_row must carry bodyweight_pct from the DB row into the Lift
    dataclass so downstream engine code (advance_lift, volume, preview) receives
    it. Guards with `in r.keys()` for older rows. (progression is gone post-ADR
    0005; bodyweight_pct remains.)"""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Chin-ups", load_model="bodyweight", mode="linear_t2",
                           day=2, sort_order=1, sets=3,
                           max=None, intensity=None, reps=None, repout=None, start=0.0,
                           bodyweight_pct=1.0)
    row = repo.get_lift(conn, lid)
    lift = advance._lift_from_row(row)
    assert lift.bodyweight_pct == 1.0
    conn.close()


def test_profile_from_rows_maps_bodyweight(tmp_path):
    """_profile_from_rows must carry bodyweight from settings into Profile so
    the engine's working_weight() can use it. Guards with `in settings.keys()`
    for older rows."""
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    repo.update_settings(conn, bodyweight=75.0)
    p = advance._profile_from_rows(repo.get_settings(conn), [], [])
    assert p.bodyweight == 75.0
    conn.close()

