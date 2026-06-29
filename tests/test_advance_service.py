import sqlite3
from webapp import db, repo
from webapp.services import advance


def _seed(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    ids = {}
    ids["Squat"] = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                                    sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    ids["Rows"] = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=1,
                                   sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    ids["Curl"] = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=2,
                                   sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    return conn, ids


def test_advance_week_runs_engine_and_bumps_week(tmp_path):
    conn, ids = _seed(tmp_path)
    new_week = advance.advance_week(conn, {ids["Squat"]: 13, ids["Rows"]: 10, ids["Curl"]: 15})
    assert new_week == 2
    assert repo.get_settings(conn)["week"] == 2
    # Squat beat repout(10) by 3 -> +1.5% -> tm 135*1.015=137.025 -> round 2.5 -> 137.5
    squat_id = ids["Squat"]
    st = repo.get_lift_state(conn, squat_id)
    assert st["tm"] == 137.5
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
    d1 = repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                          sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
    d4 = repo.create_lift(conn, name="Face Pull", tier="t3", day=4, sort_order=0,
                          sets=3, max=None, intensity=None, reps=None, repout=None, start=45.0)
    advance.advance_week(conn, {d1: 20, d4: 12})  # d1 hit (+2.5), d4 missed (unchanged)
    assert repo.get_lift_state(conn, d1)["weight"] == 32.5
    assert repo.get_lift_state(conn, d4)["weight"] == 45.0
    conn.close()
