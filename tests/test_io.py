import tempfile
import os
from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from sbs_cli.data import io as dio
from sbs_cli.data.io import save_profile, load_profile

def test_profile_roundtrip(tmp_path):
    p = Profile(rounding=2.5, days_per_week=4, lifts=[
        Lift(name="Squat", load_model="barbell", mode="sbs", day=1, max=135,
             intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", load_model="barbell", mode="linear_t2", day=1, start=85),
        Lift(name="Curls", load_model="barbell", mode="linear_t3", day=1, start=12.5),
    ])
    path = tmp_path / "profile.yaml"
    dio.save_profile(p, str(path))
    q = dio.load_profile(str(path))
    assert q.rounding == 2.5 and q.days_per_week == 4
    assert len(q.lifts) == 3
    assert q.lift("Squat").max == 135 and q.lift("Squat").intensity == 0.75
    assert q.lift("Barbell rows").start == 85 and q.lift("Barbell rows").mode == "linear_t2"
    assert q.lift("Curls").start == 12.5

def test_state_roundtrip(tmp_path):
    s = ProgramState(week=3, lifts={
        "Squat": LiftState(name="Squat", mode="sbs", tm=137.5, est1rm=158.0,
                           history=[SetEntry(1, 102.5, 8), SetEntry(2, 105, 10)]),
        "Barbell rows": LiftState(name="Barbell rows", mode="linear_t2", weight=87.5,
                                  target=10, streak=0, est1rm=110.0),
    })
    path = tmp_path / "state.yaml"
    dio.save_state(s, str(path))
    t = dio.load_state(str(path))
    assert t.week == 3
    assert t.lifts["Squat"].tm == 137.5
    assert len(t.lifts["Squat"].history) == 2
    assert t.lifts["Squat"].history[1].reps == 10
    assert t.lifts["Barbell rows"].target == 10 and t.lifts["Barbell rows"].streak == 0


def test_profile_bodyweight_and_lift_bodyweight_pct_roundtrip():
    p = Profile(bodyweight=75.0, lifts=[
        Lift(name="Chin-ups", load_model="pure_bodyweight", mode="none", day=2,
             start=0.0, bodyweight_pct=1.0),
        Lift(name="Squat", load_model="barbell", mode="sbs", day=1, max=135.0),  # ordinary: pct 0
    ])
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    try:
        save_profile(p, path)
        back = load_profile(path)
    finally:
        os.remove(path)
    assert back.bodyweight == 75.0
    chin = back.lift("Chin-ups")
    assert chin.bodyweight_pct == 1.0
    assert chin.load_model == "pure_bodyweight"
    assert chin.mode == "none"
    squat = back.lift("Squat")
    assert squat.bodyweight_pct == 0.0           # default for ordinary lifts
    assert squat.load_model == "barbell"         # default
    assert squat.mode == "sbs"


def test_legacy_yaml_without_bodyweight_fields_loads_defaults():
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, b"rounding: 2.5\nlifts:\n- name: Squat\n  load_model: barbell\n  mode: sbs\n  day: 1\n  max: 100\n")
    os.close(fd)
    try:
        back = load_profile(path)
    finally:
        os.remove(path)
    assert back.bodyweight == 0.0
    assert back.lift("Squat").bodyweight_pct == 0.0
    assert back.lift("Squat").load_model == "barbell"
    assert back.lift("Squat").mode == "sbs"
