import sqlite3
from webapp import db, repo


def _fresh(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    return conn


def test_get_settings_returns_defaults(tmp_path):
    conn = _fresh(tmp_path)
    s = repo.get_settings(conn)
    assert s["week"] == 1 and s["rounding"] == 2.5 and s["t3_target"] == 15
    conn.close()


def test_set_week_updates_week(tmp_path):
    conn = _fresh(tmp_path)
    repo.set_week(conn, 7)
    assert repo.get_settings(conn)["week"] == 7
    conn.close()


def test_update_settings_partial(tmp_path):
    conn = _fresh(tmp_path)
    repo.update_settings(conn, incr=5.0, t3_target=20)
    s = repo.get_settings(conn)
    assert s["incr"] == 5.0 and s["t3_target"] == 20 and s["rounding"] == 2.5
    conn.close()


def test_create_lift_sbs_returns_id_and_inits_state(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    assert isinstance(lid, int) and lid > 0
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "sbs" and st["tm"] == 135.0 and st["weight"] is None
    conn.close()


def test_create_lift_t2_inits_weight_target(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=1,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=85.0)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t2" and st["weight"] == 85.0 and st["target"] == 10 and st["streak"] == 0
    conn.close()


def test_create_lift_t3_inits_weight(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=2,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=40.0)
    st = repo.get_lift_state(conn, lid)
    assert st["tier"] == "t3" and st["weight"] == 40.0
    conn.close()


def test_list_and_get_lift(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    rows = repo.list_lifts(conn)
    assert len(rows) == 1 and rows[0]["name"] == "Squat"
    assert repo.get_lift(conn, lid)["name"] == "Squat"
    assert repo.get_lift_by_name(conn, "Squat")["id"] == lid
    conn.close()


def test_update_and_delete_lift(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.update_lift(conn, lid, intensity=0.75, day=2)
    assert repo.get_lift(conn, lid)["intensity"] == 0.75
    repo.delete_lift(conn, lid)
    assert repo.list_lifts(conn) == []
    assert repo.get_lift_state(conn, lid) is None  # cascade
    conn.close()


def test_create_lift_duplicate_name_raises(tmp_path):
    import pytest
    conn = _fresh(tmp_path)
    repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                     sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=1,
                         sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    conn.close()
