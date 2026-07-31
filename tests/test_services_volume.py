"""Direct unit tests for services/volume.py — tonnage_wow + live_context composer.

Previously the WoW math + HTML lived in routes/plan.py::_tonnage_html and was
only covered via HTTP (tests/test_routes_plan). Moved here as pure data fns so
the partial renders them; tests assert the data contract directly."""
from webapp import repo
from webapp.services.volume import tonnage_wow, live_context


def test_tonnage_wow_none_when_not_logged(db_conn, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    assert tonnage_wow(db_conn, lid) is None      # no week_log entry -> nothing to show


def test_tonnage_wow_first_week_marks_is_first(db_conn, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    repo.save_log(db_conn, lid, 1, 18)            # 30 * (2*15 + 18) = 1440
    t = tonnage_wow(db_conn, lid)
    assert t == {"kg": 1440.0, "pct": None, "is_first": True}


def test_tonnage_wow_two_week_delta_sign(db_conn, make_lift):
    lid = make_lift(name="Rows", mode="linear_t2", start=50.0)
    repo.append_history(db_conn, lid, week=1, weight=50.0, reps=5)
    repo.append_history(db_conn, lid, week=2, weight=50.0, reps=5)
    repo.set_week(db_conn, 3)
    repo.save_log(db_conn, lid, 3, 8)
    t = tonnage_wow(db_conn, lid)
    assert t["kg"] == 1200.0                       # 50 * (2*8 + 8)
    assert t["is_first"] is False
    assert round(t["pct"]) == 41                   # (1200-850)/850 * 100


def test_live_context_none_when_reps_none(db_conn, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    assert live_context(db_conn, lid, None) is None


def test_live_context_composes_preview_and_tonnage(db_conn, make_lift):
    lid = make_lift(name="Curl", start=30.0)
    repo.save_log(db_conn, lid, 1, 18)
    ctx = live_context(db_conn, lid, 18)
    assert ctx is not None
    assert "est1rm" in ctx and "delta" in ctx
    assert ctx["tonnage"] is not None and ctx["tonnage"]["kg"] == 1440.0
