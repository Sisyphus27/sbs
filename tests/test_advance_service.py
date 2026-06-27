import sqlite3
from webapp import db, repo
from webapp.services import advance


def _seed(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                     sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=1,
                     sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=2,
                     sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    return conn


def test_advance_week_runs_engine_and_bumps_week(tmp_path):
    conn = _seed(tmp_path)
    new_week = advance.advance_week(conn, {"Squat": 13, "Rows": 10, "Curl": 15})
    assert new_week == 2
    assert repo.get_settings(conn)["week"] == 2
    # Squat beat repout(10) by 3 -> +1.5% -> tm 135*1.015=137.025 -> round 2.5 -> 137.5
    squat_id = repo.get_lift_by_name(conn, "Squat")["id"]
    st = repo.get_lift_state(conn, squat_id)
    assert st["tm"] == 137.5
    # history appended for logged lift
    assert len(repo.list_history(conn, squat_id)) == 1
    conn.close()


def test_advance_week_skips_unlogged_lifts(tmp_path):
    conn = _seed(tmp_path)
    advance.advance_week(conn, {"Squat": 10})  # Rows/Curl not logged
    curl_id = repo.get_lift_by_name(conn, "Curl")["id"]
    assert repo.list_history(conn, curl_id) == []   # no history
    assert repo.get_lift_state(conn, curl_id)["weight"] == 40.0  # unchanged
    conn.close()


def test_advance_week_rows_t2_hit_increments(tmp_path):
    conn = _seed(tmp_path)
    advance.advance_week(conn, {"Rows": 10})  # hit target 10 -> +incr 2.5
    rows_id = repo.get_lift_by_name(conn, "Rows")["id"]
    assert repo.get_lift_state(conn, rows_id)["weight"] == 87.5
    conn.close()
