from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from sbs_cli.data import io as dio

def test_profile_roundtrip(tmp_path):
    p = Profile(rounding=2.5, days_per_week=4, lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=135, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", tier="t2", day=1, start=85),
        Lift(name="Curls", tier="t3", day=1, start=12.5),
    ])
    path = tmp_path / "profile.yaml"
    dio.save_profile(p, str(path))
    q = dio.load_profile(str(path))
    assert q.rounding == 2.5 and q.days_per_week == 4
    assert len(q.lifts) == 3
    assert q.lift("Squat").max == 135 and q.lift("Squat").intensity == 0.75
    assert q.lift("Barbell rows").start == 85 and q.lift("Barbell rows").tier == "t2"
    assert q.lift("Curls").start == 12.5

def test_state_roundtrip(tmp_path):
    s = ProgramState(week=3, lifts={
        "Squat": LiftState(name="Squat", tier="sbs", tm=137.5, est1rm=158.0,
                           history=[SetEntry(1, 102.5, 8), SetEntry(2, 105, 10)]),
        "Barbell rows": LiftState(name="Barbell rows", tier="t2", weight=87.5, target=10, streak=0,
                                  est1rm=110.0),
    })
    path = tmp_path / "state.yaml"
    dio.save_state(s, str(path))
    t = dio.load_state(str(path))
    assert t.week == 3
    assert t.lifts["Squat"].tm == 137.5
    assert len(t.lifts["Squat"].history) == 2
    assert t.lifts["Squat"].history[1].reps == 10
    assert t.lifts["Barbell rows"].target == 10 and t.lifts["Barbell rows"].streak == 0
