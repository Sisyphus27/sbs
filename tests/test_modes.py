"""Tests for the progression-mode registry (ADR 0005)."""
import pytest
from sbs_cli.data.schema import Lift, LiftState, Profile, ScheduleRow
from sbs_cli.engine.modes import PROGRESSION_REGISTRY, get_mode


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
