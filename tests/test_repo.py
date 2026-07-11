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
    assert st["tier"] == "t2" and st["weight"] == 85.0 and st["target"] == 8 and st["streak"] == 0
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


def test_create_lift_allows_duplicate_name_different_day(tmp_path):
    """Same exercise on different days = two independent rows (keyed by id, not name)."""
    conn = _fresh(tmp_path)
    a = repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
    b = repo.create_lift(conn, name="Face Pull", tier="t3", day=4, sort_order=0,
                         sets=3, max=None, intensity=None, reps=None, repout=None, start=45.0)
    assert a != b
    assert len([r for r in repo.list_lifts(conn) if r["name"] == "Face Pull"]) == 2
    conn.close()


def test_save_lift_state_upserts(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.save_lift_state(conn, lid, tier="sbs", tm=140.0, weight=None,
                         target=None, streak=0, est1rm=141.2, _append_history=False)
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 140.0 and st["est1rm"] == 141.2
    conn.close()


def test_append_history_and_list(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    repo.append_history(conn, lid, week=1, weight=95.0, reps=11)
    repo.append_history(conn, lid, week=2, weight=97.5, reps=9)
    rows = repo.list_history(conn, lid)
    assert len(rows) == 2
    assert rows[0]["week"] == 1 and rows[0]["weight"] == 95.0 and rows[0]["reps"] == 11
    assert rows[1]["week"] == 2
    conn.close()


def test_week_log_upsert_get_clear(tmp_path):
    conn = _fresh(tmp_path)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=135.0, intensity=0.7, reps=5, repout=10, start=None)
    assert repo.get_week_logs(conn, 1) == {}
    repo.save_log(conn, lid, 1, 11)
    assert repo.get_week_logs(conn, 1) == {lid: 11}
    repo.save_log(conn, lid, 1, 12)  # upsert overwrites
    assert repo.get_week_logs(conn, 1) == {lid: 12}
    repo.clear_one_log(conn, lid, 1)
    assert repo.get_week_logs(conn, 1) == {}
    repo.save_log(conn, lid, 1, 11)
    repo.save_log(conn, lid, 2, 9)   # different week, independent
    repo.clear_week_logs(conn, 1)
    assert repo.get_week_logs(conn, 1) == {}
    assert repo.get_week_logs(conn, 2) == {lid: 9}
    conn.close()


# ---------- Task 5: sbs_schedule + lift_kind + reseeded_cycle ----------


def test_init_schema_seeds_schedule(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        rows = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
        assert rows == 42


def test_get_and_replace_schedule(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        assert len(repo.get_schedule(conn)) == 42
        # replace with a single edited row
        repo.replace_schedule(conn, [("main", 1, 0.71, 5, 10)])
        got = repo.get_schedule(conn)
        assert len(got) == 1 and got[0]["intensity"] == 0.71


def test_reset_schedule_restores_defaults(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        repo.replace_schedule(conn, [("main", 1, 0.99, 1, 1)])
        repo.reset_schedule(conn)
        assert len(repo.get_schedule(conn)) == 42


def test_load_schedule_returns_dataclasses(app):
    from webapp.db import connect
    from sbs_cli.data.schema import ScheduleRow
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        rows = repo.load_schedule(conn)
        assert len(rows) == 42
        assert all(isinstance(r, ScheduleRow) for r in rows)
        assert rows[0].kind in ("main", "aux")


def test_save_lift_state_does_not_clobber_reseeded_cycle(app):
    """advance_week must not reset reseeded_cycle to 0 every week (ADR 0002)."""
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_reseed(conn, lid, cycle=2)               # stamp it
        # simulate an advance-week UPSERT (no reseeded_cycle passed)
        repo.save_lift_state(conn, lid, tier="sbs", tm=101.5, weight=None,
                             target=None, streak=0, est1rm=None)
        assert repo.get_lift_state(conn, lid)["reseeded_cycle"] == 2   # preserved


def test_create_lift_accepts_lift_kind(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        assert repo.get_lift(conn, lid)["lift_kind"] == "main"


def test_set_reseed_writes_max_tm_and_cycle(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_reseed(conn, lid, new_max=120.0, cycle=2)
        assert repo.get_lift(conn, lid)["max"] == 120.0
        st = repo.get_lift_state(conn, lid)
        assert st["tm"] == 120.0
        assert st["reseeded_cycle"] == 2


def test_set_reseed_skip_keeps_tm_advances_cycle(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                               sets=5, max=100.0, intensity=None, reps=None, repout=None,
                               start=None, lift_kind="main")
        repo.set_reseed(conn, lid, cycle=2)  # no new_max -> skip
        st = repo.get_lift_state(conn, lid)
        assert st["tm"] == 100.0            # unchanged
        assert st["reseeded_cycle"] == 2


# ---------- per-lift incr ----------

def test_create_lift_accepts_incr_and_round_trips(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Face Pull", tier="t3", day=2, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=30.0, incr=5.0)
        assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_create_lift_incr_defaults_null(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Curls", tier="t3", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=40.0)  # no incr -> NULL -> inherit global
        assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_changes_incr(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0)
        repo.update_lift(conn, lid, incr=5.0)
        assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_update_lift_can_clear_incr_to_null(app):
    from webapp.db import connect
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0, incr=5.0)
        repo.update_lift(conn, lid, incr=None)
        assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_rejects_unknown_column(app):
    # _LIFT_COLS 守卫：incr 已纳入，但拼错的列名仍必须拒绝
    from webapp.db import connect
    import pytest
    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                               sets=3, max=None, intensity=None, reps=None, repout=None,
                               start=85.0)
        with pytest.raises(ValueError):
            repo.update_lift(conn, lid, not_a_column=1)
