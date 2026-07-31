from sbs_cli.data.schema import Lift, Profile, SetEntry, LiftState, ProgramState, ScheduleRow
from sbs_cli.engine.onerm import best_1rm, est1rm_from_history
from sbs_cli.program import (initial_state,
                             advance_lift, week_plan,
                             recompute_state, recompute_sbs_tm)


def _profile():
    # Profile carries a 1-week schedule so sbs engine paths (week_plan, advance_lift,
    # recompute_sbs_tm) can read intensity/reps/repout via lookup_schedule.
    # Schedule row for week 1 mirrors the legacy static Lift fields (0.75 / 4 / 8).
    sched = [ScheduleRow("main", 1, 0.75, 4, 8)]
    return Profile(
        lifts=[
            Lift(name="Squat", mode="sbs", day=1, max=100, intensity=0.75,
                 reps=4, repout=8, sets=3, lift_kind="main"),
            Lift(name="Barbell rows", mode="linear_t2", day=1, start=50),
            Lift(name="Curls", mode="linear_t3", day=1, start=40),
        ],
        schedule=sched,
    )


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
    # TM progressed: beat repout 8 by 3 -> +1.5% -> 100*1.015 = 101.5 (raw, no MROUND)
    assert s.lifts["Squat"].tm == 101.5


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
    p = Profile(t3_target=20, incr=5, lifts=[Lift(name="Curls", mode="linear_t3", day=1, start=40)])
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
    p = Profile(t2_reset_pct=0.60, lifts=[Lift(name="Row", mode="linear_t2", day=1, start=50)])
    s = initial_state(p)
    ls = s.lifts["Row"]
    advance_lift(p, p.lift("Row"), ls, actual_reps=10, week=1)   # seed best set 50x10
    est = ls.est1rm
    ls.target, ls.streak = 4, 2
    advance_lift(p, p.lift("Row"), ls, actual_reps=3, week=4)    # 3rd miss @4 -> reset
    assert ls.weight == round_weight(est * 0.60)                 # uses 0.60, not default 0.75


def test_recompute_state_t3_replays_hits_and_misses():
    from sbs_cli.engine.onerm import est1rm_from_history
    p = Profile(lifts=[Lift(name="Curls", mode="linear_t3", day=1, start=40)])
    lift = p.lift("Curls")
    hist = [SetEntry(1, 42.5, 16), SetEntry(2, 45.0, 14), SetEntry(3, 45.0, 16)]
    ls = recompute_state(lift, hist, p)
    # replay from 40: w1 16>=15 hit -> 42.5; w2 14<15 miss -> 42.5; w3 16>=15 hit -> 45.0
    assert ls.mode == "linear_t3" and ls.weight == 45.0 and ls.target is None and ls.streak == 0
    # est1rm drawn from the real history weights (Option A) -- unchanged by start
    assert ls.est1rm == est1rm_from_history(hist)


def test_recompute_state_t2_all_hits_increments_from_start():
    from sbs_cli.engine.onerm import est1rm_from_history
    p = Profile(lifts=[Lift(name="Row", mode="linear_t2", day=1, start=50)])
    lift = p.lift("Row")
    hist = [SetEntry(1, 50.0, 8), SetEntry(2, 52.5, 8), SetEntry(3, 55.0, 8)]
    ls = recompute_state(lift, hist, p)
    # 3 hits @ target 8 -> 50 -> 52.5 -> 55.0 -> 57.5
    assert ls.weight == 57.5 and ls.target == 8 and ls.streak == 0
    assert ls.est1rm == est1rm_from_history(hist)


def test_recompute_state_t2_one_miss_drops_to_6():
    p = Profile(lifts=[Lift(name="Row", mode="linear_t2", day=1, start=50)])
    lift = p.lift("Row")
    # 1-strike: a single miss at target 8 drops to target 6, weight unchanged
    hist = [SetEntry(1, 50.0, 5)]
    ls = recompute_state(lift, hist, p)
    assert ls.target == 6 and ls.streak == 1 and ls.weight == 50.0


def test_recompute_state_empty_history_seeds_start():
    p = Profile(lifts=[
        Lift(name="Row", mode="linear_t2", day=1, start=65),
        Lift(name="Curls", mode="linear_t3", day=1, start=40),
    ])
    assert recompute_state(p.lift("Row"), [], p) == LiftState(
        name="Row", mode="linear_t2", weight=65, target=8, streak=0, est1rm=None, history=[])
    assert recompute_state(p.lift("Curls"), [], p) == LiftState(
        name="Curls", mode="linear_t3", weight=40, target=None, streak=0, est1rm=None, history=[])


def test_recompute_state_sbs_raises():
    import pytest
    p = Profile(lifts=[Lift(name="Squat", mode="sbs", day=1, max=100, intensity=0.75, reps=4, repout=8)])
    with pytest.raises(ValueError):
        recompute_state(p.lift("Squat"), [], p)


def test_sbs_tm_raw_accumulation_unfreezes_weight():
    # Beat repout by 1 each week -> +0.5%/week. Under the old bug the TM was
    # rounded each week, freezing the weight at 95 forever. With raw TM the
    # weight must climb in legal 2.5 steps.
    # Schedule: weeks 1..8 all at (0.7, 4, 8) — preserves the legacy single-intensity intent.
    sched = [ScheduleRow("main", w, 0.7, 4, 8) for w in range(1, 9)]
    p = Profile(lifts=[Lift(name="Squat", mode="sbs", day=1, max=135, sets=3, lift_kind="main")],
                schedule=sched)
    s = initial_state(p); lift = p.lift("Squat")
    weights = []
    for week in range(1, 9):
        advance_lift(p, lift, s.lifts["Squat"], actual_reps=9, week=week)
        weights.append(week_plan(p, s, day=1)[0].weight)
    assert s.lifts["Squat"].tm % 2.5 != 0          # (a) TM stays raw, not snapped
    assert weights[-1] > weights[0]                # (b) weight climbs -- stall fixed
    assert all(w % 2.5 == 0 for w in weights)      # (c) every loaded weight legal


# ---- Task 4: schedule-driven sbs engine paths ----

def _profile_with_schedule():
    sched = [ScheduleRow("main", w, i, r, ro) for (w, i, r, ro) in
             [(1, 0.70, 5, 10), (2, 0.75, 4, 8), (3, 0.80, 3, 6)]]
    lifts = [Lift(name="Squat", mode="sbs", day=1, max=100.0, sets=5, lift_kind="main")]
    return Profile(rounding=2.5, lifts=lifts, schedule=sched)


def test_week_plan_uses_scheduled_intensity_reps_repout_at_week_2():
    p = _profile_with_schedule()
    st = ProgramState(week=2, lifts={"Squat": LiftState(name="Squat", mode="sbs", tm=100.0)})
    items = week_plan(p, st, day=1)
    squat = items[0]
    # week 2 schedule: 0.75 / 4 / 8 ; weight = MROUND(100*0.75, 2.5) = 75.0
    assert squat.weight == 75.0
    assert squat.reps == 4
    assert squat.repout == 8
    assert squat.sets == 5


def test_advance_lift_uses_scheduled_repout_for_tm_delta():
    p = _profile_with_schedule()
    lift = p.lift("Squat")
    st = LiftState(name="Squat", mode="sbs", tm=100.0)
    # week 2 scheduled repout = 8; actual 11 -> beat by 3 -> +1.5% -> 101.5
    advance_lift(p, lift, st, actual_reps=11, week=2)
    assert st.tm == 101.5


def test_recompute_sbs_tm_uses_schedule_repout_per_week():
    p = _profile_with_schedule()
    lift = p.lift("Squat")
    hist = [SetEntry(week=1, weight=70.0, reps=12),   # W1 repout 10 -> beat by 2 -> +1% -> 101.0
            SetEntry(week=2, weight=75.0, reps=10)]   # W2 repout 8 -> beat by 2 -> +1% -> 102.01
    tm = recompute_sbs_tm(lift, hist, p.schedule)
    assert tm == round(100.0 * 1.01 * 1.01, 10)


# ---- per-lift eff_incr 解析 (D1/D3) ----

def test_advance_t3_uses_per_lift_incr_over_global():
    # lift.incr=5 覆盖 profile.incr=2.5；HIT 时 40+5=45（旧实现用 profile.incr=2.5 -> 42.5）
    p = Profile(incr=2.5, lifts=[Lift(name="Curls", mode="linear_t3", day=1, start=40, incr=5)])
    s = initial_state(p)
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=16, week=1)  # 16>=15 hit
    assert s.lifts["Curls"].weight == 45.0


def test_advance_t3_null_incr_falls_back_to_global():
    # incr=None -> eff_incr=profile.incr=2.5；40+2.5=42.5（向后兼容）
    p = Profile(incr=2.5, lifts=[Lift(name="Curls", mode="linear_t3", day=1, start=40)])
    s = initial_state(p)
    advance_lift(p, p.lift("Curls"), s.lifts["Curls"], actual_reps=16, week=1)
    assert s.lifts["Curls"].weight == 42.5


def test_advance_sbs_ignores_incr():
    # sbs 路径不沾 incr：working weight = round(TM*intensity, rounding)
    sched = [ScheduleRow("main", 1, 0.75, 4, 8)]
    p = Profile(rounding=2.5, schedule=sched,
                lifts=[Lift(name="Squat", mode="sbs", day=1, max=100, sets=3,
                            lift_kind="main", incr=99)])
    s = initial_state(p)
    advance_lift(p, p.lift("Squat"), s.lifts["Squat"], actual_reps=8, week=1)
    assert s.lifts["Squat"].history[0].weight == 75  # round(100*0.75, 2.5)=75, incr=99 被忽略


def test_recompute_state_t2_reset_snaps_to_eff_incr():
    # recompute 重放：incr=5 的 t2，reset 重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5
    from sbs_cli.engine.progression import round_weight
    from sbs_cli.engine.onerm import est1rm_from_history
    p = Profile(t2_reset_pct=0.75, incr=2.5, rounding=2.5,
                lifts=[Lift(name="PD", mode="linear_t2", day=1, start=100, incr=5)])
    lift = p.lift("PD")
    # 最佳组 100x5 -> est1rm≈115；×0.75≈86.4 落在 5-grid(85) 与 2.5-grid(87.5) 之间
    hist = [SetEntry(1, 100.0, 5), SetEntry(2, 100.0, 3),
            SetEntry(3, 100.0, 3), SetEntry(4, 100.0, 3)]  # 1 hit 后 3 连 miss -> reset
    ls = recompute_state(lift, hist, p)
    est = est1rm_from_history(hist)
    assert ls.weight == round_weight(est * 0.75, 5)       # NEW: eff_incr 网格
    assert ls.weight != round_weight(est * 0.75, 2.5)     # OLD: 全局 rounding 会给不同值


# -- Task 3: bodyweight working-weight seam (best_1rm / est1rm_from_history) --

from sbs_cli.engine.onerm import estimate_1rm


def test_best_1rm_bodyweight_uses_working_weight_not_added():
    # chin-up: added 0, bw 75, pct 1.0, reps 5 -> working weight 75
    hist = [SetEntry(week=1, weight=0.0, reps=5)]
    bw, reps = best_1rm(hist, bodyweight=75.0, bodyweight_pct=1.0)
    assert bw == 75.0
    assert reps == 5


def test_est1rm_from_history_bodyweight_nonzero():
    hist = [SetEntry(week=1, weight=0.0, reps=5)]
    est = est1rm_from_history(hist, bodyweight=75.0, bodyweight_pct=1.0)
    assert est == estimate_1rm(75.0, 5)
    assert est > 0.0


def test_est1rm_from_history_ordinary_lift_unchanged():
    # pct 0 -> working weight == added; legacy behavior preserved
    hist = [SetEntry(week=1, weight=100.0, reps=5)]
    est = est1rm_from_history(hist, bodyweight=75.0, bodyweight_pct=0.0)
    assert est == estimate_1rm(100.0, 5)


# -- Task 4: recompute_state threads bodyweight into est1RM + T2 reset --

def test_recompute_state_t2_bodyweight_reset_uses_working_weight():
    # Chin-ups (linear_t2, pct 1.0). Force 3 consecutive misses -> reset to
    # round(est1rm * 0.75, incr). est1rm must be computed from working weight
    # (bodyweight + added), not added alone -- otherwise reset weight collapses
    # toward 0. DEViation from brief: reps=3 (not 5) so week 3 at target=4 is
    # still a MISS; with reps=5 the ladder cascade makes W3 a HIT at target=4
    # (5>=4) so the reset path never fires and the fix would not be exercised.
    lift = Lift(name="Chin-ups", mode="linear_t2", day=2, start=0.0,
                bodyweight_pct=1.0, incr=2.5)
    profile = Profile(bodyweight=75.0, incr=2.5, t2_fail=3, t2_reset_pct=0.75)
    hist = [SetEntry(week=1, weight=0.0, reps=3),
            SetEntry(week=2, weight=0.0, reps=3),
            SetEntry(week=3, weight=0.0, reps=3)]
    ls = recompute_state(lift, hist, profile)
    # reset weight should be on the order of est1rm(75, 3) * 0.75 ~ 60 kg,
    # NOT near 0. Assert it is plainly bodyweight-driven:
    assert ls.weight > 50.0


# -- Task 5: advance_lift progression="none" + working-weight est1RM --

def _bw_profile(**kw):
    return Profile(bodyweight=75.0, incr=2.5, t3_target=15, **kw)


def test_advance_lift_progression_none_skips_weight_progression():
    # High Crunch: pure_bodyweight/none. Hit target (15) -> state.weight
    # must NOT gain incr (no phantom added weight).
    lift = Lift(name="High Crunch", load_model="pure_bodyweight", mode="none",
                day=4, start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="High Crunch", mode="none", weight=0.0)
    p = _bw_profile(schedule=[])  # none doesn't need schedule
    advance_lift(p, lift, state, actual_reps=20, week=1)
    assert state.weight == 0.0           # unchanged -- no +2.5 phantom added
    assert state.est1rm is not None and state.est1rm > 0.0   # est1rm from bw


def test_advance_lift_linear_t3_still_increments_added():
    # Dips (bodyweight/linear_t3, pct 1.0). Hit target -> +incr to ADDED weight.
    lift = Lift(name="Dips", load_model="bodyweight", mode="linear_t3",
                day=4, start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="Dips", mode="linear_t3", weight=0.0)
    p = _bw_profile(schedule=[])
    advance_lift(p, lift, state, actual_reps=20, week=1)
    assert state.weight == 2.5           # added grew by incr


def test_advance_lift_bodyweight_history_stores_added_not_working():
    # Dips (linear_t3, pct 1.0): recorded history weight is the ADDED weight (0.0),
    # not the working weight (75) -- the load seam is applied only at est1rm/display.
    lift = Lift(name="Dips", load_model="bodyweight", mode="linear_t3",
                day=4, start=0.0, bodyweight_pct=1.0)
    state = LiftState(name="Dips", mode="linear_t3", weight=0.0)
    p = _bw_profile(schedule=[])
    advance_lift(p, lift, state, actual_reps=10, week=1)
    assert state.history[-1].weight == 0.0    # added, NOT 75


# -- Task 6: week_plan exposes working weight for bodyweight lifts (CLI display) --

def test_week_plan_bodyweight_t2_shows_working_weight_not_zero():
    # Chin-ups (linear_t2, pct 1.0): ls.weight=0 (added) -> PlanItem.weight must be
    # working weight = 0 + 75*1.0 = 75, not the legacy raw 0.
    lift = Lift(name="Chin-ups", load_model="bodyweight", mode="linear_t2",
                day=2, start=0.0, bodyweight_pct=1.0)
    p = Profile(bodyweight=75.0, incr=2.5, lifts=[lift], schedule=[])
    st = ProgramState(week=1, lifts={"Chin-ups":
        LiftState(name="Chin-ups", mode="linear_t2", weight=0.0, target=8)})
    items = week_plan(p, st, day=2)
    assert len(items) == 1
    assert items[0].weight == 75.0    # working weight, not 0.0
    assert items[0].mode == "linear_t2"   # ADR 0005: PlanItem carries mode, not tier
