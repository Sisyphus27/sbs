from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState
from sbs_cli.program import best_1rm, initial_state, advance_lift, week_plan, recompute_state


def _profile():
    return Profile(lifts=[
        Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8, sets=3),
        Lift(name="Barbell rows", tier="t2", day=1, start=50),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])


def test_best_1rm_picks_max_estimate():
    hist = [SetEntry(1, 80, 5), SetEntry(2, 85, 9), SetEntry(3, 90, 3)]
    b = best_1rm(hist)
    # 85x9 yields the highest est1rm of the three
    assert b is not None and b[0] == 85 and b[1] == 9


def test_best_1rm_empty_returns_none():
    assert best_1rm([]) is None


def test_initial_state_sbs_uses_max_as_tm():
    p = _profile(); s = initial_state(p)
    assert s.lifts["Squat"].tm == 100
    assert s.lifts["Barbell rows"].weight == 50 and s.lifts["Barbell rows"].target == 8
    assert s.lifts["Curls"].weight == 40


def test_advance_sbs_appends_history_and_updates_est1rm():
    p = _profile(); s = initial_state(p)
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=11, week=1)
    # working weight was round(100*0.75)=75; logged; est1rm computed from (75,11)
    assert len(s.lifts["Squat"].history) == 1
    assert s.lifts["Squat"].history[0].weight == 75 and s.lifts["Squat"].history[0].reps == 11
    assert s.lifts["Squat"].est1rm is not None
    # TM progressed: beat repout 8 by 3 -> +1.5% -> 100*1.015=101.5 -> MROUND 102.5
    assert s.lifts["Squat"].tm == 102.5


def test_advance_t2_reset_uses_best_set_est1rm():
    from sbs_cli.engine.progression import round_weight
    p = _profile(); s = initial_state(p)
    ls = s.lifts["Barbell rows"]
    # seed a best set: 50x10 -> est1rm ~ 67
    advance_lift(p, p.lift("Barbell rows"), ls, actual_reps=10, week=1)
    est = ls.est1rm
    # now force 3 consecutive misses at the bottom (target 4) -> reset @ 75%
    ls.target, ls.streak = 4, 2
    advance_lift(p, p.lift("Barbell rows"), ls, actual_reps=3, week=4)   # 3rd miss at 4 -> reset
    assert ls.target == 8 and ls.streak == 0
    assert ls.weight == round_weight(est * 0.75)                      # 0.75*est, MROUND 2.5


def test_week_plan_sbs_shows_working_weight():
    p = _profile(); s = initial_state(p)
    plan = week_plan(p, s, day=1)
    squat = next(item for item in plan if item.name == "Squat")
    # working weight = round(100*0.75, 2.5) = 75; reps 4, sets 3
    assert squat.weight == 75 and squat.reps == 4 and squat.sets == 3 and squat.repout == 8


def test_advance_t3_uses_profile_target_and_incr():
    # non-default knobs: t3_target=20, incr=5
    p = Profile(t3_target=20, incr=5, lifts=[Lift(name="Curls", tier="t3", day=1, start=40)])
    s = initial_state(p)
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=16, week=1)
    # 16 < target 20 -> miss -> weight repeats (NOT a hit at hardcoded 15)
    assert s.lifts["Curls"].weight == 40
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=20, week=2)
    # 20 >= target 20 -> hit -> +incr(5) -> 45
    assert s.lifts["Curls"].weight == 45


def test_advance_t2_reset_uses_profile_reset_pct():
    from sbs_cli.engine.progression import round_weight
    # non-default reset_pct=0.60
    p = Profile(t2_reset_pct=0.60, lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    s = initial_state(p)
    ls = s.lifts["Row"]
    advance_lift(p, p.lift("Row"), ls, actual_reps=10, week=1)   # seed best set 50x10
    est = ls.est1rm
    ls.target, ls.streak = 4, 2
    advance_lift(p, p.lift("Row"), ls, actual_reps=3, week=4)    # 3rd miss @4 -> reset
    assert ls.weight == round_weight(est * 0.60)                 # uses 0.60, not default 0.75


def test_recompute_state_t3_replays_hits_and_misses():
    from sbs_cli.program import _est1rm_from_history
    p = Profile(lifts=[Lift(name="Curls", tier="t3", day=1, start=40)])
    lift = p.lift("Curls")
    hist = [SetEntry(1, 42.5, 16), SetEntry(2, 45.0, 14), SetEntry(3, 45.0, 16)]
    ls = recompute_state(lift, hist, p)
    # replay from 40: w1 16>=15 hit -> 42.5; w2 14<15 miss -> 42.5; w3 16>=15 hit -> 45.0
    assert ls.tier == "t3" and ls.weight == 45.0 and ls.target is None and ls.streak == 0
    # est1rm drawn from the real history weights (Option A) -- unchanged by start
    assert ls.est1rm == _est1rm_from_history(hist)


def test_recompute_state_t2_all_hits_increments_from_start():
    from sbs_cli.program import _est1rm_from_history
    p = Profile(lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    lift = p.lift("Row")
    hist = [SetEntry(1, 50.0, 8), SetEntry(2, 52.5, 8), SetEntry(3, 55.0, 8)]
    ls = recompute_state(lift, hist, p)
    # 3 hits @ target 8 -> 50 -> 52.5 -> 55.0 -> 57.5
    assert ls.weight == 57.5 and ls.target == 8 and ls.streak == 0
    assert ls.est1rm == _est1rm_from_history(hist)


def test_recompute_state_t2_cascade_drops_to_6():
    p = Profile(lifts=[Lift(name="Row", tier="t2", day=1, start=50)])
    lift = p.lift("Row")
    # 3 consecutive misses at target 8 (reps 5 < 8) -> drop to target 6, weight unchanged
    hist = [SetEntry(1, 50.0, 5), SetEntry(2, 50.0, 5), SetEntry(3, 50.0, 5)]
    ls = recompute_state(lift, hist, p)
    assert ls.target == 6 and ls.streak == 0 and ls.weight == 50.0


def test_recompute_state_empty_history_seeds_start():
    p = Profile(lifts=[
        Lift(name="Row", tier="t2", day=1, start=65),
        Lift(name="Curls", tier="t3", day=1, start=40),
    ])
    assert recompute_state(p.lift("Row"), [], p) == LiftState(
        name="Row", tier="t2", weight=65, target=8, streak=0, est1rm=None, history=[])
    assert recompute_state(p.lift("Curls"), [], p) == LiftState(
        name="Curls", tier="t3", weight=40, target=None, streak=0, est1rm=None, history=[])


def test_recompute_state_sbs_raises():
    import pytest
    p = Profile(lifts=[Lift(name="Squat", tier="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8)])
    with pytest.raises(ValueError):
        recompute_state(p.lift("Squat"), [], p)
