from webapp import repo


def test_get_settings_returns_defaults(legacy_conn):
    conn = legacy_conn
    s = repo.get_settings(conn)
    assert s["week"] == 1 and s["rounding"] == 2.5 and s["t3_target"] == 15


def test_set_week_updates_week(legacy_conn):
    conn = legacy_conn
    repo.set_week(conn, 7)
    assert repo.get_settings(conn)["week"] == 7


def test_update_settings_partial(legacy_conn):
    conn = legacy_conn
    repo.update_settings(conn, incr=5.0, t3_target=20)
    s = repo.get_settings(conn)
    assert s["incr"] == 5.0 and s["t3_target"] == 20 and s["rounding"] == 2.5


def test_create_lift_sbs_returns_id_and_inits_state(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
    assert isinstance(lid, int) and lid > 0
    st = repo.get_lift_state(conn, lid)
    assert st["mode"] == "sbs" and st["tm"] == 135.0 and st["weight"] is None


def test_create_lift_t2_inits_weight_target(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=1, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=85.0)
    st = repo.get_lift_state(conn, lid)
    assert st["mode"] == "linear_t2" and st["weight"] == 85.0 and st["target"] == 8 and st["streak"] == 0


def test_create_lift_t3_inits_weight(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Curl", load_model="barbell", mode="linear_t3",
                           day=1, sort_order=2, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=40.0)
    st = repo.get_lift_state(conn, lid)
    assert st["mode"] == "linear_t3" and st["weight"] == 40.0


def test_list_and_get_lift(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
    rows = repo.list_lifts(conn)
    assert len(rows) == 1 and rows[0]["name"] == "Squat"
    assert repo.get_lift(conn, lid)["name"] == "Squat"
    assert repo.get_lift_by_name(conn, "Squat")["id"] == lid


def test_update_and_delete_lift(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
    repo.update_lift(conn, lid, intensity=0.75, day=2)
    assert repo.get_lift(conn, lid)["intensity"] == 0.75
    repo.delete_lift(conn, lid)
    assert repo.list_lifts(conn) == []
    assert repo.get_lift_state(conn, lid) is None  # cascade


def test_create_lift_allows_duplicate_name_different_day(legacy_conn):
    """Same exercise on different days = two independent rows (keyed by id, not name)."""
    conn = legacy_conn
    a = repo.create_lift(conn, name="Face Pull", load_model="barbell", mode="linear_t3",
                         day=2, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=30.0)
    b = repo.create_lift(conn, name="Face Pull", load_model="barbell", mode="linear_t3",
                         day=4, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=45.0)
    assert a != b
    assert len([r for r in repo.list_lifts(conn) if r["name"] == "Face Pull"]) == 2


def test_save_lift_state_upserts(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
    repo.save_lift_state(conn, lid, mode="sbs", tm=140.0, weight=None,
                         target=None, streak=0, est1rm=141.2)
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 140.0 and st["est1rm"] == 141.2


def test_append_history_and_list(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
    repo.append_history(conn, lid, week=1, weight=95.0, reps=11)
    repo.append_history(conn, lid, week=2, weight=97.5, reps=9)
    rows = repo.list_history(conn, lid)
    assert len(rows) == 2
    assert rows[0]["week"] == 1 and rows[0]["weight"] == 95.0 and rows[0]["reps"] == 11
    assert rows[1]["week"] == 2


def test_week_log_upsert_get_clear(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=135.0, intensity=0.7,
                           reps=5, repout=10, start=None)
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


# ---------- Task 5: sbs_schedule + lift_kind + reseeded_cycle ----------


def test_init_schema_seeds_schedule(legacy_conn):
    conn = legacy_conn
    rows = conn.execute("SELECT COUNT(*) FROM sbs_schedule").fetchone()[0]
    assert rows == 42


def test_get_and_replace_schedule(legacy_conn):
    conn = legacy_conn
    assert len(repo.get_schedule(conn)) == 42
    # replace with a single edited row
    repo.replace_schedule(conn, [("main", 1, 0.71, 5, 10)])
    got = repo.get_schedule(conn)
    assert len(got) == 1 and got[0]["intensity"] == 0.71


def test_reset_schedule_restores_defaults(legacy_conn):
    conn = legacy_conn
    repo.replace_schedule(conn, [("main", 1, 0.99, 1, 1)])
    repo.reset_schedule(conn)
    assert len(repo.get_schedule(conn)) == 42


def test_load_schedule_returns_dataclasses(legacy_conn):
    from sbs_cli.data.schema import ScheduleRow
    conn = legacy_conn
    rows = repo.load_schedule(conn)
    assert len(rows) == 42
    assert all(isinstance(r, ScheduleRow) for r in rows)
    assert rows[0].kind in ("main", "aux")


def test_save_lift_state_does_not_clobber_reseeded_cycle(legacy_conn):
    """advance_week must not reset reseeded_cycle to 0 every week (ADR 0002)."""
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                           reps=None, repout=None, start=None, lift_kind="main")
    repo.set_reseed(conn, lid, cycle=2)               # stamp it
    # simulate an advance-week UPSERT (no reseeded_cycle passed)
    repo.save_lift_state(conn, lid, mode="sbs", tm=101.5, weight=None,
                         target=None, streak=0, est1rm=None)
    assert repo.get_lift_state(conn, lid)["reseeded_cycle"] == 2   # preserved


def test_create_lift_accepts_lift_kind(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                           reps=None, repout=None, start=None, lift_kind="main")
    assert repo.get_lift(conn, lid)["lift_kind"] == "main"


def test_set_reseed_writes_max_tm_and_cycle(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                           reps=None, repout=None, start=None, lift_kind="main")
    repo.set_reseed(conn, lid, new_max=120.0, cycle=2)
    assert repo.get_lift(conn, lid)["max"] == 120.0
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 120.0
    assert st["reseeded_cycle"] == 2


def test_set_reseed_skip_keeps_tm_advances_cycle(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Squat", load_model="barbell", mode="sbs",
                           day=1, sort_order=0, sets=5, max=100.0, intensity=None,
                           reps=None, repout=None, start=None, lift_kind="main")
    repo.set_reseed(conn, lid, cycle=2)  # no new_max -> skip
    st = repo.get_lift_state(conn, lid)
    assert st["tm"] == 100.0            # unchanged
    assert st["reseeded_cycle"] == 2


# ---------- per-lift incr ----------

def test_create_lift_accepts_incr_and_round_trips(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Face Pull", load_model="barbell", mode="linear_t3",
                           day=2, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=30.0, incr=5.0)
    assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_create_lift_incr_defaults_null(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Curls", load_model="barbell", mode="linear_t3",
                           day=1, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=40.0)  # no incr -> NULL -> inherit global
    assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_changes_incr(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=85.0)
    repo.update_lift(conn, lid, incr=5.0)
    assert repo.get_lift(conn, lid)["incr"] == 5.0


def test_update_lift_can_clear_incr_to_null(legacy_conn):
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=85.0, incr=5.0)
    repo.update_lift(conn, lid, incr=None)
    assert repo.get_lift(conn, lid)["incr"] is None


def test_update_lift_rejects_unknown_column(legacy_conn):
    # _LIFT_COLS 守卫：incr 已纳入，但拼错的列名仍必须拒绝
    import pytest
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Rows", load_model="barbell", mode="linear_t2",
                           day=1, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=85.0)
    with pytest.raises(ValueError):
        repo.update_lift(conn, lid, not_a_column=1)


# ---------- ADR 0005: load_model/mode + bodyweight_pct ----------

def test_create_lift_stores_load_model_mode_and_bodyweight_pct(legacy_conn):
    """create_lift persists load_model/mode (ADR 0005) and round-trips bodyweight_pct."""
    conn = legacy_conn
    # pure_bodyweight/none is the pure-bodyweight legal combo (pull-up/dip)
    lid = repo.create_lift(conn, name="Dips", load_model="pure_bodyweight", mode="none",
                           day=4, sort_order=1, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=0.0, bodyweight_pct=1.0)
    row = repo.get_lift(conn, lid)
    assert row["load_model"] == "pure_bodyweight"
    assert row["mode"] == "none"
    assert row["bodyweight_pct"] == 1.0


def test_create_lift_bodyweight_pct_defaults_zero(legacy_conn):
    """Omitting bodyweight_pct must default to 0.0 (legacy callers)."""
    conn = legacy_conn
    lid = repo.create_lift(conn, name="Pull-up", load_model="barbell", mode="linear_t3",
                           day=2, sort_order=0, sets=3, max=None, intensity=None,
                           reps=None, repout=None, start=30.0)
    row = repo.get_lift(conn, lid)
    assert row["bodyweight_pct"] == 0.0


def test_create_lift_rejects_illegal_load_model_mode_combo(legacy_conn):
    """is_legal_combo guard: pure_bodyweight must pair with none, not sbs."""
    import pytest
    conn = legacy_conn
    with pytest.raises(ValueError):
        repo.create_lift(conn, name="Bad", load_model="pure_bodyweight", mode="sbs",
                         day=1, sort_order=0, sets=3, max=None, intensity=None,
                         reps=None, repout=None, start=None)


def test_get_settings_returns_bodyweight_default(legacy_conn):
    """Fresh DB seeds settings.bodyweight = 0.0 (Task 7)."""
    conn = legacy_conn
    s = repo.get_settings(conn)
    assert s["bodyweight"] == 0.0
