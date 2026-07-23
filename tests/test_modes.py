"""Tests for the progression-mode registry (ADR 0005)."""
import pytest
from sbs_cli.data.schema import Lift, LiftState, Profile, ScheduleRow, SetEntry
from sbs_cli.engine.modes import PROGRESSION_REGISTRY, get_mode
from sbs_cli.engine.onerm import estimate_1rm
from sbs_cli.engine.progression import round_weight


def _sched():
    return [ScheduleRow(kind="main", week=1, intensity=0.70, reps=5, repout=10)]


def test_registry_keys():
    assert set(PROGRESSION_REGISTRY) == {"sbs", "linear_t2", "linear_t3", "none"}


def test_get_mode_unknown_raises():
    with pytest.raises(KeyError):
        get_mode("bogus")


def test_sbs_initial_state():
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", max=100.0)
    s = get_mode("sbs").initial_state(l, None)
    assert s.mode == "sbs" and s.tm == 100.0


def test_t2_initial_state():
    l = Lift(name="Bp", day=1, load_model="barbell", mode="linear_t2", start=60.0)
    s = get_mode("linear_t2").initial_state(l, None)
    assert s.mode == "linear_t2" and s.weight == 60.0 and s.target == 8


def test_t3_initial_state():
    l = Lift(name="Curl", day=1, load_model="barbell", mode="linear_t3", start=20.0)
    s = get_mode("linear_t3").initial_state(l, None)
    assert s.mode == "linear_t3" and s.weight == 20.0 and s.target is None


def test_none_initial_state():
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none")
    s = get_mode("none").initial_state(l, None)
    assert s.mode == "none" and s.target is None


def test_none_advance_records_only():
    p = Profile(bodyweight=75.0, schedule=_sched())
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none", bodyweight_pct=1.0)
    s = LiftState(name="Pu", mode="none", weight=0.0)
    get_mode("none").advance(p, l, s, 12, week=1)
    assert s.weight == 0.0            # no progression
    assert len(s.history) == 1        # recorded
    assert s.est1rm is not None       # est1rm recomputed (bw x pct=75 @12 reps)


def test_sbs_advance_tm():
    p = Profile(rounding=2.5, schedule=_sched())
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", lift_kind="main")
    s = LiftState(name="Sq", mode="sbs", tm=100.0)
    get_mode("sbs").advance(p, l, s, 12, week=1)   # repout=10, beat by 2 -> +1%
    assert s.tm == pytest.approx(101.0)


# ---- plan_fields: each handler returns the 5 display fields ----

def test_sbs_plan_fields_uses_schedule():
    # TM 100, week-1 schedule 0.70 / reps 5 / repout 10 -> weight 70, reps 5
    p = Profile(rounding=2.5, schedule=_sched())
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", lift_kind="main")
    s = LiftState(name="Sq", mode="sbs", tm=100.0)
    f = get_mode("sbs").plan_fields(p, l, s, week=1)
    assert f["weight"] == 70.0
    assert f["reps"] == 5
    assert f["repout"] == 10
    assert f["target"] is None
    assert f["streak"] == 0


def test_linear_t2_plan_fields_reads_state_target_streak():
    p = Profile(bodyweight=0.0)  # no bw, working weight == added
    l = Lift(name="Row", day=1, load_model="barbell", mode="linear_t2")
    s = LiftState(name="Row", mode="linear_t2", weight=50.0, target=6, streak=2)
    f = get_mode("linear_t2").plan_fields(p, l, s, week=3)
    assert f["weight"] == 50.0
    assert f["reps"] == 6            # current ladder target
    assert f["repout"] is None
    assert f["target"] == 6
    assert f["streak"] == 2


def test_linear_t3_plan_fields_uses_profile_target():
    p = Profile(t3_target=15)
    l = Lift(name="Curl", day=1, load_model="barbell", mode="linear_t3")
    s = LiftState(name="Curl", mode="linear_t3", weight=40.0)
    f = get_mode("linear_t3").plan_fields(p, l, s, week=1)
    assert f["weight"] == 40.0
    assert f["reps"] == 15           # profile.t3_target
    assert f["repout"] is None
    assert f["target"] == 15
    assert f["streak"] == 0


def test_none_plan_fields_uses_last_reps_when_history_exists():
    p = Profile(bodyweight=75.0, schedule=[])
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none", bodyweight_pct=1.0)
    s = LiftState(name="Pu", mode="none", weight=0.0,
                  history=[SetEntry(week=1, weight=0.0, reps=12)])
    f = get_mode("none").plan_fields(p, l, s, week=2)
    assert f["weight"] == 75.0       # working weight
    assert f["reps"] == 12           # last logged reps
    assert f["repout"] is None
    assert f["target"] is None
    assert f["streak"] == 0


def test_none_plan_fields_reps_none_when_history_empty():
    p = Profile(bodyweight=75.0, schedule=[])
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none", bodyweight_pct=1.0)
    s = LiftState(name="Pu", mode="none", weight=0.0)
    f = get_mode("none").plan_fields(p, l, s, week=1)
    assert f["reps"] is None         # no history yet
    assert f["weight"] == 75.0


# ---- derive_on_switch: per-mode starting-state derivation ----

def test_sbs_derive_on_switch_uses_est1rm_when_present():
    # ADR 0001: switching to sbs seeds TM from est1rm when available.
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", max=80.0)
    settings = {}
    d = get_mode("sbs").derive_on_switch(lift=l, history=[], settings=settings, est1rm=120.0)
    assert d["mode"] == "sbs"
    assert d["tm"] == 120.0          # est1rm wins over lift.max
    assert d["weight"] is None
    assert d["target"] is None
    assert d["streak"] == 0


def test_sbs_derive_on_switch_falls_back_to_max_when_est1rm_none():
    # No history -> est1rm None -> TM falls back to lift.max (ADR 0001)
    l = Lift(name="Sq", day=1, load_model="barbell", mode="sbs", max=90.0)
    d = get_mode("sbs").derive_on_switch(lift=l, history=[], settings={}, est1rm=None)
    assert d["tm"] == 90.0


def test_linear_t2_derive_on_switch_seeds_reset_pct_of_est1rm():
    # est1rm known -> weight = round(est1rm * t2_reset_pct, eff_incr)
    l = Lift(name="Row", day=1, load_model="barbell", mode="linear_t2", start=50.0, incr=2.5)
    settings = {"incr": 2.5, "t2_reset_pct": 0.75}
    d = get_mode("linear_t2").derive_on_switch(lift=l, history=[], settings=settings, est1rm=100.0)
    assert d["mode"] == "linear_t2"
    assert d["tm"] is None
    assert d["weight"] == round_weight(100.0 * 0.75, 2.5)   # 75.0
    assert d["target"] == 8
    assert d["streak"] == 0


def test_linear_t2_derive_on_switch_est1rm_none_uses_start():
    l = Lift(name="Row", day=1, load_model="barbell", mode="linear_t2", start=60.0)
    d = get_mode("linear_t2").derive_on_switch(lift=l, history=[], settings={"incr": 2.5}, est1rm=None)
    assert d["weight"] == 60.0       # fallback to lift.start


def test_linear_t3_derive_on_switch_seeds_60pct_of_est1rm():
    # T3 switch: weight = round(est1rm * 0.6, eff_incr); target None.
    l = Lift(name="Curl", day=1, load_model="barbell", mode="linear_t3", start=20.0, incr=2.5)
    d = get_mode("linear_t3").derive_on_switch(lift=l, history=[], settings={"incr": 2.5}, est1rm=100.0)
    assert d["mode"] == "linear_t3"
    assert d["tm"] is None
    assert d["weight"] == round_weight(100.0 * 0.6, 2.5)   # 60.0
    assert d["target"] is None
    assert d["streak"] == 0


def test_linear_t3_derive_on_switch_est1rm_none_uses_start():
    l = Lift(name="Curl", day=1, load_model="barbell", mode="linear_t3", start=22.5)
    d = get_mode("linear_t3").derive_on_switch(lift=l, history=[], settings={"incr": 2.5}, est1rm=None)
    assert d["weight"] == 22.5


def test_none_derive_on_switch_seeds_start():
    l = Lift(name="Pu", day=1, load_model="pure_bodyweight", mode="none", start=0.0)
    d = get_mode("none").derive_on_switch(lift=l, history=[], settings={}, est1rm=999.0)
    # none ignores est1rm entirely: weight = lift.start
    assert d["mode"] == "none"
    assert d["tm"] is None
    assert d["weight"] == 0.0
    assert d["target"] is None
    assert d["streak"] == 0
