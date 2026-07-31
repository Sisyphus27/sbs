"""Direct unit tests for services/reseed.py::due_lifts (ADR 0002 cycle-boundary).

Previously _due_lifts lived as a private fn in routes/reseed.py and was only
covered indirectly via HTTP (tests/test_routes_reseed.py). The move to a public
service home adds a direct seam to assert the cycle-boundary predicate."""
from sbs_cli.engine.progression import cycle_number
from webapp import repo
from webapp.services.reseed import due_lifts


def _sbs(db_conn, name="Squat", sort_order=0):
    return repo.create_lift(db_conn, name=name, load_model="barbell", mode="sbs",
                            day=1, sort_order=sort_order, sets=5, max=100.0,
                            intensity=None, reps=None, repout=None, start=None,
                            lift_kind="main")


def test_due_lifts_empty_before_cycle_boundary(db_conn):
    """Week 2 = cycle 1, schedule_week 2 -> not a reseed boundary."""
    repo.set_week(db_conn, 2)
    _sbs(db_conn)
    due, cyc = due_lifts(db_conn)
    assert due == []
    assert cyc == cycle_number(2)


def test_due_lifts_lists_sbs_at_cycle2_week22(db_conn):
    """Week 22 = schedule_week 1, cycle 2, reseeded_cycle 0 -> due."""
    repo.set_week(db_conn, 22)
    lid = _sbs(db_conn)
    due, cyc = due_lifts(db_conn)
    assert cyc == 2
    assert len(due) == 1
    r, st = due[0]
    assert r["id"] == lid and r["mode"] == "sbs"
    assert (st["reseeded_cycle"] or 0) < cyc


def test_due_lifts_skips_non_sbs(db_conn):
    """Only sbs lifts reseed; linear modes are never listed."""
    repo.set_week(db_conn, 22)
    _sbs(db_conn)
    repo.create_lift(db_conn, name="Curl", load_model="barbell", mode="linear_t3",
                     day=1, sort_order=1, sets=3, max=None, intensity=None,
                     reps=None, repout=None, start=40.0)
    due, _ = due_lifts(db_conn)
    assert len(due) == 1                       # only the sbs lift
    assert due[0][0]["name"] == "Squat"


def test_due_lifts_skips_already_reseeded(db_conn):
    """A lift whose reseeded_cycle has caught up to the current cycle is not due."""
    repo.set_week(db_conn, 22)
    lid = _sbs(db_conn)
    repo.set_reseed(db_conn, lid, cycle=2)      # stamped to cycle 2 already
    due, cyc = due_lifts(db_conn)
    assert cyc == 2
    assert due == []                            # reseeded_cycle 2 is not < 2
