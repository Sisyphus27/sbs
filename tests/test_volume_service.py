from webapp.services.volume import _actual_tonnage


def test_actual_tonnage_basic():
    # 100kg, 3 sets, planned 8, last set 10 -> 100 * (2*8 + 10) = 2600
    assert _actual_tonnage(100.0, 3, 8, 10) == 2600.0


def test_actual_tonnage_single_set():
    # sets=1 -> (1-1)*planned + last = last only -> 100 * 10 = 1000
    assert _actual_tonnage(100.0, 1, 8, 10) == 1000.0


def test_actual_tonnage_zero_or_none_sets_falls_back_to_3():
    assert _actual_tonnage(100.0, 0, 8, 10) == 2600.0
    assert _actual_tonnage(100.0, None, 8, 10) == 2600.0


from webapp import db, repo
from webapp.services.volume import _t2_target_as_of


def _t2(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=50.0)
    return conn, lid


def test_t2_target_as_of_initial_when_no_prior_history(tmp_path):
    # target_week=1 -> replay weeks<1 = [] -> initial target 8
    conn, lid = _t2(tmp_path)
    assert _t2_target_as_of(conn, lid, 1) == 8
    conn.close()


def test_t2_target_as_of_replays_miss_drop(tmp_path):
    # week1 logged 5 reps (< target 8) -> miss -> target drops 8->6.
    # target_week=2 -> replay weeks<2 = [week1] -> target entering week2 = 6.
    conn, lid = _t2(tmp_path)
    repo.append_history(conn, lid, week=1, weight=50.0, reps=5)
    assert _t2_target_as_of(conn, lid, 2) == 6
    conn.close()


from webapp.services.volume import lift_week_volume


def _sbs(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Squat", tier="sbs", day=1, sort_order=0,
                           sets=5, max=100.0, intensity=0.7, reps=5, repout=10,
                           start=None, lift_kind="main")
    repo.save_lift_state(conn, lid, tier="sbs", tm=100.0, weight=None,
                         target=None, streak=0, est1rm=None)
    return conn, lid


def test_volume_current_sbs(tmp_path):
    # tm=100, week1 main: intensity 0.70 -> weight=70, planned reps=5, sets=5.
    # logged last=10 -> 70 * (4*5 + 10) = 70 * 30 = 2100
    conn, lid = _sbs(tmp_path)
    repo.save_log(conn, lid, 1, 10)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 2100.0
    conn.close()


def test_volume_current_not_logged_returns_none(tmp_path):
    conn, lid = _sbs(tmp_path)
    assert lift_week_volume(conn, lid, 1, is_current=True) is None
    conn.close()


def test_volume_past_week_from_history(tmp_path):
    # last week (week1): history weight 70, reps 10, planned 5, sets 5 -> 2100
    conn, lid = _sbs(tmp_path)
    repo.set_week(conn, 2)
    repo.append_history(conn, lid, week=1, weight=70.0, reps=10)
    assert lift_week_volume(conn, lid, 1, is_current=False) == 2100.0
    conn.close()


def test_volume_past_week_missing_returns_none(tmp_path):
    conn, lid = _sbs(tmp_path)
    assert lift_week_volume(conn, lid, 1, is_current=False) is None
    conn.close()


def test_volume_current_t3(tmp_path):
    # t3 start=30, sets=3, t3_target=15, logged last=18 -> 30 * (2*15 + 18) = 30*48 = 1440
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Curl", tier="t3", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=30.0)
    repo.save_log(conn, lid, 1, 18)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 1440.0
    conn.close()


def test_volume_current_t2(tmp_path):
    # t2 start=50, target=8 (initial), sets=3, logged last=8 -> 50 * (2*8 + 8) = 50*24 = 1200
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    lid = repo.create_lift(conn, name="Rows", tier="t2", day=1, sort_order=0,
                           sets=3, max=None, intensity=None, reps=None, repout=None, start=50.0)
    repo.save_log(conn, lid, 1, 8)
    assert lift_week_volume(conn, lid, 1, is_current=True) == 1200.0
    conn.close()


def test_lift_week_volume_bodyweight_past_week_uses_working_weight(tmp_path):
    # Dips, t3, bodyweight_pct=1.0, settings.bodyweight=75.
    # Prior-week history row: added 0, reps 12, t3_target=15 (default), sets=3.
    # working weight = 0 + 75*1.0 = 75 -> 75 * (2*15 + 12) = 75 * 42 = 3150.
    # RED until history branch routes through working_weight seam (was raw row["weight"]=0 -> 0).
    conn = db.connect(str(tmp_path / "t.db"))
    db.init_schema(conn)
    repo.update_settings(conn, bodyweight=75.0)
    lid = repo.create_lift(conn, name="Dips", tier="t3", day=4, sort_order=1, sets=3,
                           max=None, intensity=None, reps=None, repout=None, start=0.0,
                           bodyweight_pct=1.0)
    repo.save_lift_state(conn, lid, tier="t3", tm=None, weight=0.0, target=None,
                         streak=0, est1rm=None)
    repo.append_history(conn, lid, week=1, weight=0.0, reps=12)
    tonnage = lift_week_volume(conn, lid, week=1, is_current=False)
    assert tonnage == 75.0 * (2 * 15 + 12)
    conn.close()
