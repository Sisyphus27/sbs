from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState

def test_lift_sbs_construction():
    l = Lift(name="Squat", tier="sbs", day=1, max=135, intensity=0.75, reps=4, repout=8, sets=3)
    assert l.tier == "sbs" and l.max == 135 and l.start is None

def test_lift_t2_construction():
    l = Lift(name="Barbell rows", tier="t2", day=1, start=85)
    assert l.max is None and l.start == 85

def test_profile_defaults():
    p = Profile()
    assert p.rounding == 2.5 and p.days_per_week == 4 and p.t2_reset_pct == 0.75
    assert p.lifts == []

def test_setentry_and_liftstate():
    s = SetEntry(week=1, weight=100, reps=9)
    ls = LiftState(name="Squat", tier="sbs", tm=135, est1rm=158.0, history=[s])
    assert ls.history[0].reps == 9

def test_programstate_holds_lifts_by_name():
    ps = ProgramState(week=1, lifts={"Squat": LiftState(name="Squat", tier="sbs", tm=135)})
    assert "Squat" in ps.lifts and ps.lifts["Squat"].tm == 135

from sbs_cli.data.schema import Lift


def test_lift_incr_defaults_to_none():
    # NULL = 继承全局 settings.incr（live inheritance）
    l = Lift(name="Face Pull", tier="t3", day=2)
    assert l.incr is None


def test_lift_incr_can_be_set():
    l = Lift(name="Pull-downs", tier="t2", day=1, incr=5.0)
    assert l.incr == 5.0


# --- Task 1 (ADR 0005): dual load_model/mode enums ---
from sbs_cli.data.schema import (Lift, LiftState, LOAD_MODELS, MODES,
                                 LEGAL_COMBOS, is_legal_combo)


def test_lift_has_load_model_and_mode():
    l = Lift(name="Pull-up", load_model="pure_bodyweight", mode="none", day=1)
    assert l.load_model == "pure_bodyweight"
    assert l.mode == "none"
    assert l.bodyweight_pct == 0.0


def test_lift_defaults():
    l = Lift(name="Bench", day=1)
    assert l.load_model == "barbell"
    assert l.mode == "none"  # default; caller sets a legal one


def test_liftstate_mode_field():
    s = LiftState(name="x", mode="sbs", tm=100.0)
    assert s.mode == "sbs"


def test_legal_combos():
    assert is_legal_combo("barbell", "sbs")
    assert is_legal_combo("barbell", "linear_t2")
    assert is_legal_combo("barbell", "linear_t3")
    assert is_legal_combo("bodyweight", "linear_t2")
    assert is_legal_combo("bodyweight", "linear_t3")
    assert is_legal_combo("pure_bodyweight", "none")
    # illegal
    assert not is_legal_combo("barbell", "none")
    assert not is_legal_combo("bodyweight", "none")
    assert not is_legal_combo("bodyweight", "sbs")
    assert not is_legal_combo("pure_bodyweight", "sbs")
    assert not is_legal_combo("pure_bodyweight", "linear_t2")
    assert not is_legal_combo("pure_bodyweight", "linear_t3")
