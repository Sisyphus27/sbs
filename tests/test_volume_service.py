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
