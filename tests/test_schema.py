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
