"""Behavior guards (ADR 0004): bodyweight lifts must never compute est1RM/tonnage
from raw added weight. If a future change reintroduces a raw-weight path, the
fixture (bw 75, added 0) yields 0 and these fail."""
import sqlite3
from webapp.db import init_schema
from webapp.repo import (create_lift, update_settings, save_lift_state,
                         append_history, get_lift_state)
from sbs_cli.engine.onerm import estimate_1rm


def _seed_bodyweight_db():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    init_schema(conn)
    update_settings(conn, bodyweight=75.0)
    return conn


def test_guard_preview_est1rm_is_bodyweight_driven():
    from webapp.services.preview import live_preview
    conn = _seed_bodyweight_db()
    lid = create_lift(conn, name="Chin-ups", load_model="bodyweight", mode="linear_t2",
                      day=2, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    assert live_preview(conn, lid, 5)["est1rm"] == estimate_1rm(75.0, 5)
    conn.close()


def test_guard_volume_tonnage_is_bodyweight_driven():
    from webapp.services.volume import lift_week_volume
    conn = _seed_bodyweight_db()
    lid = create_lift(conn, name="Dips", load_model="bodyweight", mode="linear_t3",
                      day=4, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    save_lift_state(conn, lid, mode="linear_t3", tm=None, weight=0.0, target=None,
                    streak=0, est1rm=None)
    append_history(conn, lid, week=1, weight=0.0, reps=12)
    assert lift_week_volume(conn, lid, 1, is_current=False) == 75.0 * (2 * 15 + 12)
    conn.close()


def test_guard_advance_progression_none_keeps_added_zero():
    from sbs_cli.program import advance_lift
    from sbs_cli.data.schema import Lift, LiftState, Profile
    lift = Lift(name="Crunch", load_model="pure_bodyweight", mode="none", day=4,
                start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="Crunch", mode="none", weight=0.0)
    advance_lift(Profile(bodyweight=75.0, incr=2.5, t3_target=15, schedule=[]),
                 lift, state, 20, 1)
    assert state.weight == 0.0
    assert state.est1rm == estimate_1rm(75.0, 20)


def test_guard_advance_t2_reset_uses_working_weight():
    from sbs_cli.program import advance_lift
    from sbs_cli.data.schema import Lift, LiftState, Profile
    # Chin-ups linear_t2: drive 3 misses so a reset fires; reset weight must be bodyweight-scale.
    lift = Lift(name="Chin-ups", load_model="bodyweight", mode="linear_t2", day=2,
                start=0.0, bodyweight_pct=1.0, incr=2.5)
    state = LiftState(name="Chin-ups", mode="linear_t2", weight=0.0, target=8, streak=0)
    p = Profile(bodyweight=75.0, incr=2.5, t2_fail=3, t2_reset_pct=0.75, schedule=[])
    for _ in range(3):
        advance_lift(p, lift, state, 3, 1)   # miss each time
    assert state.weight > 50.0   # reset to ~est1rm(75,3)*0.75, not near 0


def test_guard_mode_switch_derive_state_is_bodyweight_driven():
    """ADR 0004 guard: mode.derive_state (preview + apply path) must thread
    bodyweight into _est1rm_from_history. A bodyweight lift (bw=75, pct=1.0,
    added=0) switched to linear_t2 must derive est1rm == estimate_1rm(75, reps),
    NOT estimate_1rm(0, reps) ~= 0. Regression for the call-site inventory miss
    in the bodyweight-working-weight plan (whole-branch review finding)."""
    from webapp.services.mode import derive_state
    from webapp.repo import get_settings
    conn = _seed_bodyweight_db()
    lid = create_lift(conn, name="Chin-ups", load_model="bodyweight", mode="linear_t3",
                      day=2, sort_order=1, sets=3,
                      max=None, intensity=None, reps=None, repout=None, start=0.0,
                      bodyweight_pct=1.0)
    # history.weight is ADDED weight (ADR 0004 seam) — 0 for a pure-bodyweight lift.
    append_history(conn, lid, week=1, weight=0.0, reps=5)  # added=0, bw=75 -> ww=75
    settings = get_settings(conn)
    derived = derive_state(conn, lid, "linear_t2", settings)
    # Load-bearing claim: est1rm is bodyweight-driven, not 0.
    assert derived["est1rm"] == estimate_1rm(75.0, 5)
    # User-visible consequence: the linear_t2 reset/start weight snaps onto a
    # bodyweight-scale grid, NOT 0. (estimate_1rm(75,5)*0.75 ~= 65.)
    assert derived["weight"] > 50.0
    conn.close()
